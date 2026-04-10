//! mq9 client — AI-native async Agent mailbox communication over NATS.
//!
//! # Example
//!
//! ```no_run
//! use robustmq::mq9::{MQ9Client, Priority};
//!
//! #[tokio::main]
//! async fn main() -> Result<(), Box<dyn std::error::Error>> {
//!     let client = MQ9Client::connect("nats://localhost:4222").await?;
//!
//!     let mailbox = client.create(3600, false, "", "").await?;
//!     client.send(&mailbox.mail_id, b"hello", Priority::Normal).await?;
//!
//!     client.close().await?;
//!     Ok(())
//! }
//! ```

use std::fmt;
use std::future::Future;
use std::sync::Arc;

use async_nats::Client as NatsClient;
use bytes::Bytes;
use futures::StreamExt as _;
use serde_json::Value;

// ---------------------------------------------------------------------------
// Subject constants
// ---------------------------------------------------------------------------

const PREFIX: &str = "$mq9.AI";
const MAILBOX_CREATE: &str = "$mq9.AI.MAILBOX.CREATE";

fn subject_msg_base(mail_id: &str) -> String {
    format!("{PREFIX}.MAILBOX.MSG.{mail_id}")
}

/// Send subject: normal uses bare (no suffix); urgent/critical append suffix.
fn subject_msg(mail_id: &str, priority: Priority) -> String {
    if priority == Priority::Normal {
        subject_msg_base(mail_id)
    } else {
        format!("{}.{}", subject_msg_base(mail_id), priority.as_str())
    }
}

/// Subscribe subject: "*" uses wildcard; normal uses bare; others append suffix.
fn subject_sub(mail_id: &str, priority: &str) -> String {
    match priority {
        "*" => format!("{}.*", subject_msg_base(mail_id)),
        "normal" => subject_msg_base(mail_id),
        p => format!("{}.{}", subject_msg_base(mail_id), p),
    }
}

fn subject_list(mail_id: &str) -> String {
    format!("{PREFIX}.MAILBOX.LIST.{mail_id}")
}

fn subject_delete(mail_id: &str, msg_id: &str) -> String {
    format!("{PREFIX}.MAILBOX.DELETE.{mail_id}.{msg_id}")
}

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/// Message priority level.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Priority {
    Critical,
    Urgent,
    Normal,
}

impl Priority {
    pub fn as_str(&self) -> &'static str {
        match self {
            Priority::Critical => "critical",
            Priority::Urgent => "urgent",
            Priority::Normal => "normal",
        }
    }

    pub fn from_str_lossy(s: &str) -> Priority {
        match s {
            "critical" => Priority::Critical,
            "urgent" => Priority::Urgent,
            _ => Priority::Normal,
        }
    }
}

impl fmt::Display for Priority {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// A created mq9 mailbox.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Mailbox {
    pub mail_id: String,
    pub public: bool,
    pub name: String,
    pub desc: String,
}

/// Metadata for a message returned by list(). Does not include payload.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MessageMeta {
    pub msg_id: String,
    pub priority: Priority,
    pub ts: i64,
}

/// A message received via subscribe().
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Message {
    pub msg_id: String,
    pub mail_id: String,
    pub priority: Priority,
    pub payload: Vec<u8>,
}

/// A raw incoming message from the transport (subject + payload bytes).
pub struct RawMsg {
    pub subject: String,
    pub payload: Bytes,
}

/// An active subscription handle.
pub struct Subscription {
    handle: tokio::task::JoinHandle<()>,
}

impl Subscription {
    /// Abort the background receive task.
    pub fn unsubscribe(self) {
        self.handle.abort();
    }
}

/// Error returned by the mq9 client.
#[derive(Debug)]
pub struct MQ9Error {
    pub message: String,
    pub code: u32,
}

impl fmt::Display for MQ9Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.code != 0 {
            write!(f, "mq9 error (code {}): {}", self.code, self.message)
        } else {
            write!(f, "mq9 error: {}", self.message)
        }
    }
}

impl std::error::Error for MQ9Error {}

// ---------------------------------------------------------------------------
// Internal NATS transport abstraction (enables unit-testing without live server)
// ---------------------------------------------------------------------------

/// A boxed stream of raw messages, used as the subscribe return type.
pub(crate) type MsgStream = std::pin::Pin<Box<dyn futures::Stream<Item = RawMsg> + Send>>;

/// Trait that abstracts the NATS operations used by [`MQ9Client`].
pub trait NatsTransport: Send + Sync + 'static {
    fn publish<'a>(
        &'a self,
        subject: String,
        payload: Bytes,
    ) -> std::pin::Pin<Box<dyn Future<Output = Result<(), MQ9Error>> + Send + 'a>>;

    fn request<'a>(
        &'a self,
        subject: String,
        payload: Bytes,
    ) -> std::pin::Pin<Box<dyn Future<Output = Result<Bytes, MQ9Error>> + Send + 'a>>;

    fn subscribe<'a>(
        &'a self,
        subject: String,
        queue_group: Option<String>,
    ) -> std::pin::Pin<Box<dyn Future<Output = Result<MsgStream, MQ9Error>> + Send + 'a>>;

    fn drain<'a>(
        &'a self,
    ) -> std::pin::Pin<Box<dyn Future<Output = Result<(), MQ9Error>> + Send + 'a>>;
}

// ---------------------------------------------------------------------------
// Real NATS transport
// ---------------------------------------------------------------------------

struct RealNats(NatsClient);

impl NatsTransport for RealNats {
    fn publish<'a>(
        &'a self,
        subject: String,
        payload: Bytes,
    ) -> std::pin::Pin<Box<dyn Future<Output = Result<(), MQ9Error>> + Send + 'a>> {
        Box::pin(async move {
            self.0
                .publish(subject, payload)
                .await
                .map_err(|e| MQ9Error {
                    message: format!("publish failed: {e}"),
                    code: 0,
                })
        })
    }

    fn request<'a>(
        &'a self,
        subject: String,
        payload: Bytes,
    ) -> std::pin::Pin<Box<dyn Future<Output = Result<Bytes, MQ9Error>> + Send + 'a>> {
        Box::pin(async move {
            let reply = self
                .0
                .request(subject, payload)
                .await
                .map_err(|e| MQ9Error {
                    message: format!("request failed: {e}"),
                    code: 0,
                })?;
            Ok(reply.payload)
        })
    }

    fn subscribe<'a>(
        &'a self,
        subject: String,
        queue_group: Option<String>,
    ) -> std::pin::Pin<Box<dyn Future<Output = Result<MsgStream, MQ9Error>> + Send + 'a>> {
        Box::pin(async move {
            let sub = if let Some(queue) = queue_group {
                self.0
                    .queue_subscribe(subject, queue)
                    .await
                    .map_err(|e| MQ9Error {
                        message: format!("queue_subscribe failed: {e}"),
                        code: 0,
                    })?
            } else {
                self.0.subscribe(subject).await.map_err(|e| MQ9Error {
                    message: format!("subscribe failed: {e}"),
                    code: 0,
                })?
            };
            // Map async_nats::Subscriber (stream of async_nats::Message) to our RawMsg stream
            let stream = sub.map(|msg| RawMsg {
                subject: msg.subject.to_string(),
                payload: msg.payload,
            });
            Ok(Box::pin(stream) as MsgStream)
        })
    }

    fn drain<'a>(
        &'a self,
    ) -> std::pin::Pin<Box<dyn Future<Output = Result<(), MQ9Error>> + Send + 'a>> {
        Box::pin(async move {
            // async-nats Client is closed by dropping it; flush pending messages
            self.0.flush().await.map_err(|e| MQ9Error {
                message: format!("flush failed: {e}"),
                code: 0,
            })
        })
    }
}

// ---------------------------------------------------------------------------
// MQ9Client
// ---------------------------------------------------------------------------

/// Async mq9 client for RobustMQ.
pub struct MQ9Client {
    transport: Arc<dyn NatsTransport>,
}

impl MQ9Client {
    /// Connect to a NATS server and return a ready client.
    pub async fn connect(server: &str) -> Result<Self, MQ9Error> {
        let nc = async_nats::connect(server).await.map_err(|e| MQ9Error {
            message: format!("connection failed: {e}"),
            code: 0,
        })?;
        Ok(MQ9Client {
            transport: Arc::new(RealNats(nc)),
        })
    }

    /// Create a client from a custom transport (used in tests).
    pub fn with_transport(transport: impl NatsTransport) -> Self {
        MQ9Client {
            transport: Arc::new(transport),
        }
    }

    /// Drain subscriptions and close the connection.
    pub async fn close(self) -> Result<(), MQ9Error> {
        self.transport.drain().await
    }

    // ------------------------------------------------------------------
    // Mailbox operations
    // ------------------------------------------------------------------

    /// Create a mailbox (private or public).
    ///
    /// For a public mailbox, `public` must be `true` and `name` must be non-empty.
    /// Operation is idempotent — repeating returns success with the original TTL.
    pub async fn create(
        &self,
        ttl: u64,
        public: bool,
        name: &str,
        desc: &str,
    ) -> Result<Mailbox, MQ9Error> {
        if public && name.is_empty() {
            return Err(MQ9Error {
                message: "name is required when public=true".into(),
                code: 0,
            });
        }

        let mut body = serde_json::json!({ "ttl": ttl });
        if public {
            body["public"] = Value::Bool(true);
            body["name"] = Value::String(name.to_string());
            if !desc.is_empty() {
                body["desc"] = Value::String(desc.to_string());
            }
        }

        let resp = self.do_request(MAILBOX_CREATE, &body).await?;
        let mail_id = resp["mail_id"]
            .as_str()
            .ok_or_else(|| MQ9Error {
                message: "create response missing mail_id".into(),
                code: 0,
            })?
            .to_string();

        Ok(Mailbox {
            mail_id,
            public,
            name: name.to_string(),
            desc: desc.to_string(),
        })
    }

    /// Send a message to a mailbox (fire-and-forget).
    pub async fn send(
        &self,
        mail_id: &str,
        payload: &[u8],
        priority: Priority,
    ) -> Result<(), MQ9Error> {
        let subject = subject_msg(mail_id, priority);
        self.transport
            .publish(subject, Bytes::copy_from_slice(payload))
            .await
    }

    /// Subscribe to incoming messages for a mailbox.
    ///
    /// `priority` = `None` subscribes to all priorities (`*`).
    /// The callback is invoked for each arriving message in a spawned task.
    ///
    /// Returns a [`Subscription`] handle; call `.unsubscribe()` to cancel.
    pub async fn subscribe<F, Fut>(
        &self,
        mail_id: &str,
        callback: F,
        priority: Option<Priority>,
        queue_group: &str,
    ) -> Result<Subscription, MQ9Error>
    where
        F: Fn(Message) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = ()> + Send + 'static,
    {
        let priority_str = priority
            .map(|p| p.as_str().to_string())
            .unwrap_or_else(|| "*".to_string());
        let subject = subject_sub(mail_id, &priority_str);
        let queue = if queue_group.is_empty() {
            None
        } else {
            Some(queue_group.to_string())
        };

        let mut stream = self.transport.subscribe(subject, queue).await?;
        let mail_id_owned = mail_id.to_string();

        let handle = tokio::spawn(async move {
            while let Some(raw) = stream.next().await {
                let message = parse_incoming(&mail_id_owned, &raw);
                callback(message).await;
            }
        });

        Ok(Subscription { handle })
    }

    /// Return a metadata snapshot of all non-expired messages in a mailbox.
    /// Does not include payloads — subscribe to receive full messages.
    pub async fn list(&self, mail_id: &str) -> Result<Vec<MessageMeta>, MQ9Error> {
        let subject = subject_list(mail_id);
        let resp = self.do_request(&subject, &serde_json::json!({})).await?;
        let metas = resp["messages"]
            .as_array()
            .map(|arr| arr.iter().filter_map(parse_message_meta).collect())
            .unwrap_or_default();
        Ok(metas)
    }

    /// Delete a specific message from a mailbox.
    pub async fn delete(&self, mail_id: &str, msg_id: &str) -> Result<(), MQ9Error> {
        let subject = subject_delete(mail_id, msg_id);
        self.do_request(&subject, &serde_json::json!({})).await?;
        Ok(())
    }

    // ------------------------------------------------------------------
    // Internal helpers
    // ------------------------------------------------------------------

    async fn do_request(&self, subject: &str, body: &Value) -> Result<Value, MQ9Error> {
        let data = Bytes::from(serde_json::to_vec(body).map_err(|e| MQ9Error {
            message: format!("serialization error: {e}"),
            code: 0,
        })?);

        let reply_bytes = self.transport.request(subject.to_string(), data).await?;

        let resp: Value = serde_json::from_slice(&reply_bytes).map_err(|e| MQ9Error {
            message: format!("invalid JSON response: {e}"),
            code: 0,
        })?;

        if let Some(err_msg) = resp.get("error").and_then(|v| v.as_str()) {
            let code = resp.get("code").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
            return Err(MQ9Error {
                message: err_msg.to_string(),
                code,
            });
        }

        Ok(resp)
    }
}

// ---------------------------------------------------------------------------
// Message parsing helpers
// ---------------------------------------------------------------------------

/// Parse a message arriving on a subscription subject.
///
/// Subject is bare `$mq9.AI.MAILBOX.MSG.{mail_id}` (normal)
/// or `$mq9.AI.MAILBOX.MSG.{mail_id}.{urgent|critical}`.
fn parse_incoming(mail_id: &str, raw: &RawMsg) -> Message {
    let base = subject_msg_base(mail_id);
    let suffix = raw.subject.strip_prefix(&base).unwrap_or("");
    let priority_str = suffix.strip_prefix('.').unwrap_or("");
    let priority = Priority::from_str_lossy(priority_str);

    // Try JSON envelope first
    if let Ok(envelope) = serde_json::from_slice::<Value>(&raw.payload) {
        if envelope.is_object() && envelope.get("msg_id").is_some() {
            let payload = envelope
                .get("payload")
                .and_then(|v| v.as_str())
                .and_then(|s| b64_decode(s).ok())
                .unwrap_or_else(|| raw.payload.to_vec());

            return Message {
                msg_id: envelope["msg_id"].as_str().unwrap_or("").to_string(),
                mail_id: mail_id.to_string(),
                priority,
                payload,
            };
        }
    }

    // Raw bytes fallback
    Message {
        msg_id: String::new(),
        mail_id: mail_id.to_string(),
        priority,
        payload: raw.payload.to_vec(),
    }
}

/// Parse a `MessageMeta` from a JSON value in a LIST response.
fn parse_message_meta(v: &Value) -> Option<MessageMeta> {
    let msg_id = v["msg_id"].as_str()?.to_string();
    let priority = Priority::from_str_lossy(v["priority"].as_str().unwrap_or("normal"));
    let ts = v["ts"].as_i64().unwrap_or(0);
    Some(MessageMeta {
        msg_id,
        priority,
        ts,
    })
}

// ---------------------------------------------------------------------------
// Minimal base64 decoder (standard alphabet with padding)
// Reuses no extra crate — async-nats brings in the `base64` crate as a dep
// but it is not re-exported, so we inline a small decoder here.
// ---------------------------------------------------------------------------

fn b64_decode(s: &str) -> Result<Vec<u8>, ()> {
    const TABLE: [u8; 128] = {
        let mut t = [255u8; 128];
        let alpha = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        let mut i = 0usize;
        while i < 64 {
            t[alpha[i] as usize] = i as u8;
            i += 1;
        }
        t['=' as usize] = 64; // padding sentinel
        t
    };

    let s = s.trim_end_matches('=');
    let mut out = Vec::with_capacity(s.len() * 3 / 4 + 1);
    let mut buf = 0u32;
    let mut bits = 0u32;

    for &c in s.as_bytes() {
        if c as usize >= 128 {
            return Err(());
        }
        let v = TABLE[c as usize];
        if v == 255 {
            return Err(());
        }
        buf = (buf << 6) | v as u32;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((buf >> bits) as u8);
            buf &= (1 << bits) - 1;
        }
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use bytes::Bytes;
    use serde_json::json;
    use std::collections::VecDeque;
    use std::sync::Mutex;

    // ------------------------------------------------------------------
    // Mock transport
    // ------------------------------------------------------------------

    /// A queued response for the mock.
    #[derive(Clone)]
    enum MockResponse {
        Ok(Bytes),
        Err { message: String, code: u32 },
    }

    struct MockTransport {
        /// Responses returned by `request()`, consumed in order.
        responses: Mutex<VecDeque<MockResponse>>,
        /// Calls recorded by `publish()`: (subject, payload)
        published: Mutex<Vec<(String, Vec<u8>)>>,
        /// Calls recorded by `request()`: (subject, payload)
        requested: Mutex<Vec<(String, Vec<u8>)>>,
        /// Calls recorded by `subscribe()`: (subject, queue_group)
        subscribed: Mutex<Vec<(String, Option<String>)>>,
        /// Pre-loaded messages to emit from subscribe() stream.
        sub_messages: Mutex<Vec<RawMsg>>,
    }

    impl MockTransport {
        fn new() -> Self {
            MockTransport {
                responses: Mutex::new(VecDeque::new()),
                published: Mutex::new(Vec::new()),
                requested: Mutex::new(Vec::new()),
                subscribed: Mutex::new(Vec::new()),
                sub_messages: Mutex::new(Vec::new()),
            }
        }

        fn push_ok(&self, body: serde_json::Value) {
            let bytes = Bytes::from(serde_json::to_vec(&body).unwrap());
            self.responses
                .lock()
                .unwrap()
                .push_back(MockResponse::Ok(bytes));
        }

        fn push_err(&self, message: &str, code: u32) {
            self.responses.lock().unwrap().push_back(MockResponse::Err {
                message: message.into(),
                code,
            });
        }

        /// Pre-load a message that will be emitted when subscribe() is called.
        fn push_sub_msg(&self, subject: impl Into<String>, payload: impl Into<Vec<u8>>) {
            self.sub_messages.lock().unwrap().push(RawMsg {
                subject: subject.into(),
                payload: Bytes::from(payload.into()),
            });
        }

        fn published(&self) -> Vec<(String, Vec<u8>)> {
            self.published.lock().unwrap().clone()
        }

        fn requested(&self) -> Vec<(String, Vec<u8>)> {
            self.requested.lock().unwrap().clone()
        }

        fn subscribed(&self) -> Vec<(String, Option<String>)> {
            self.subscribed.lock().unwrap().clone()
        }
    }

    impl NatsTransport for MockTransport {
        fn publish<'a>(
            &'a self,
            subject: String,
            payload: Bytes,
        ) -> std::pin::Pin<Box<dyn Future<Output = Result<(), MQ9Error>> + Send + 'a>> {
            self.published
                .lock()
                .unwrap()
                .push((subject, payload.to_vec()));
            Box::pin(async { Ok(()) })
        }

        fn request<'a>(
            &'a self,
            subject: String,
            payload: Bytes,
        ) -> std::pin::Pin<Box<dyn Future<Output = Result<Bytes, MQ9Error>> + Send + 'a>> {
            self.requested
                .lock()
                .unwrap()
                .push((subject, payload.to_vec()));
            let resp = self.responses.lock().unwrap().pop_front();
            Box::pin(async move {
                match resp {
                    Some(MockResponse::Ok(b)) => Ok(b),
                    Some(MockResponse::Err { message, code }) => {
                        // Return a JSON error envelope so do_request can parse it
                        let body = json!({ "error": message, "code": code });
                        Ok(Bytes::from(serde_json::to_vec(&body).unwrap()))
                    }
                    None => Err(MQ9Error {
                        message: "no mock response queued".into(),
                        code: 0,
                    }),
                }
            })
        }

        fn subscribe<'a>(
            &'a self,
            subject: String,
            queue_group: Option<String>,
        ) -> std::pin::Pin<Box<dyn Future<Output = Result<MsgStream, MQ9Error>> + Send + 'a>>
        {
            self.subscribed.lock().unwrap().push((subject, queue_group));
            // Drain the pre-loaded messages into a stream that yields them all then ends.
            let messages: Vec<RawMsg> = self.sub_messages.lock().unwrap().drain(..).collect();
            Box::pin(async move {
                let stream = futures::stream::iter(messages);
                Ok(Box::pin(stream) as MsgStream)
            })
        }

        fn drain<'a>(
            &'a self,
        ) -> std::pin::Pin<Box<dyn Future<Output = Result<(), MQ9Error>> + Send + 'a>> {
            Box::pin(async { Ok(()) })
        }
    }

    fn make_client(mock: MockTransport) -> MQ9Client {
        MQ9Client::with_transport(mock)
    }

    // ------------------------------------------------------------------
    // create
    // ------------------------------------------------------------------

    #[tokio::test]
    async fn test_create_private_mailbox() {
        let mock = MockTransport::new();
        mock.push_ok(json!({ "mail_id": "m-abc-001" }));
        let client = make_client(mock);

        let mailbox = client.create(3600, false, "", "").await.unwrap();

        assert_eq!(mailbox.mail_id, "m-abc-001");
        assert!(!mailbox.public);
        assert_eq!(mailbox.name, "");
        assert_eq!(mailbox.desc, "");
    }

    #[tokio::test]
    async fn test_create_private_request_subject_and_body() {
        let mock = Arc::new(MockTransport::new());
        mock.push_ok(json!({ "mail_id": "m-001" }));
        let arc = mock.clone();
        let client = MQ9Client { transport: mock };

        client.create(3600, false, "", "").await.unwrap();

        let calls = arc.requested();
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0].0, "$mq9.AI.MAILBOX.CREATE");
        let body: serde_json::Value = serde_json::from_slice(&calls[0].1).unwrap();
        assert_eq!(body, json!({ "ttl": 3600 }));
    }

    #[tokio::test]
    async fn test_create_public_mailbox() {
        let mock = MockTransport::new();
        mock.push_ok(json!({ "mail_id": "task.queue" }));
        let client = make_client(mock);

        let mailbox = client
            .create(86400, true, "task.queue", "Task queue")
            .await
            .unwrap();

        assert_eq!(mailbox.mail_id, "task.queue");
        assert!(mailbox.public);
        assert_eq!(mailbox.name, "task.queue");
        assert_eq!(mailbox.desc, "Task queue");
    }

    #[tokio::test]
    async fn test_create_public_requires_name() {
        let mock = MockTransport::new();
        let client = make_client(mock);

        let result = client.create(3600, true, "", "").await;
        assert!(result.is_err());
        let err = result.unwrap_err();
        assert!(err.message.contains("name is required"));
    }

    #[tokio::test]
    async fn test_create_public_request_body() {
        let mock = Arc::new(MockTransport::new());
        mock.push_ok(json!({ "mail_id": "task.queue" }));
        let arc = mock.clone();
        let client = MQ9Client { transport: mock };

        client
            .create(86400, true, "task.queue", "Tasks")
            .await
            .unwrap();

        let calls = arc.requested();
        let body: serde_json::Value = serde_json::from_slice(&calls[0].1).unwrap();
        assert_eq!(body["public"], json!(true));
        assert_eq!(body["name"], json!("task.queue"));
        assert_eq!(body["desc"], json!("Tasks"));
        assert_eq!(body["ttl"], json!(86400));
    }

    #[tokio::test]
    async fn test_create_server_error() {
        let mock = MockTransport::new();
        mock.push_err("quota exceeded", 429);
        let client = make_client(mock);

        let result = client.create(3600, false, "", "").await;
        assert!(result.is_err());
        let err = result.unwrap_err();
        assert_eq!(err.code, 429);
        assert!(err.message.contains("quota exceeded"));
    }

    // ------------------------------------------------------------------
    // send
    // ------------------------------------------------------------------

    #[tokio::test]
    async fn test_send_normal_priority() {
        let mock = Arc::new(MockTransport::new());
        let arc = mock.clone();
        let client = MQ9Client { transport: mock };

        client
            .send("m-001", b"hello", Priority::Normal)
            .await
            .unwrap();

        let calls = arc.published();
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0].0, "$mq9.AI.MAILBOX.MSG.m-001.normal");
        assert_eq!(calls[0].1, b"hello");
    }

    #[tokio::test]
    async fn test_send_high_priority() {
        let mock = Arc::new(MockTransport::new());
        let arc = mock.clone();
        let client = MQ9Client { transport: mock };

        client
            .send("m-001", b"urgent", Priority::High)
            .await
            .unwrap();

        let calls = arc.published();
        assert_eq!(calls[0].0, "$mq9.AI.MAILBOX.MSG.m-001.high");
    }

    #[tokio::test]
    async fn test_send_low_priority() {
        let mock = Arc::new(MockTransport::new());
        let arc = mock.clone();
        let client = MQ9Client { transport: mock };

        client.send("m-001", b"lazy", Priority::Low).await.unwrap();

        let calls = arc.published();
        assert_eq!(calls[0].0, "$mq9.AI.MAILBOX.MSG.m-001.low");
    }

    #[tokio::test]
    async fn test_send_payload_preserved() {
        let mock = Arc::new(MockTransport::new());
        let arc = mock.clone();
        let client = MQ9Client { transport: mock };
        let payload = b"binary\x00data\xff";

        client
            .send("m-001", payload, Priority::Normal)
            .await
            .unwrap();

        assert_eq!(&arc.published()[0].1, payload);
    }

    // ------------------------------------------------------------------
    // list
    // ------------------------------------------------------------------

    // ------------------------------------------------------------------
    // subscribe
    // ------------------------------------------------------------------

    #[tokio::test]
    async fn test_subscribe_all_priorities_subject() {
        let mock = Arc::new(MockTransport::new());
        let arc = mock.clone();
        let client = MQ9Client { transport: mock };

        let _sub = client
            .subscribe("m-001", |_msg| async {}, None, "")
            .await
            .unwrap();

        let calls = arc.subscribed();
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0].0, "$mq9.AI.MAILBOX.MSG.m-001.*");
        assert_eq!(calls[0].1, None);
    }

    #[tokio::test]
    async fn test_subscribe_single_priority_subject() {
        let mock = Arc::new(MockTransport::new());
        let arc = mock.clone();
        let client = MQ9Client { transport: mock };

        let _sub = client
            .subscribe("m-001", |_msg| async {}, Some(Priority::High), "")
            .await
            .unwrap();

        let calls = arc.subscribed();
        assert_eq!(calls[0].0, "$mq9.AI.MAILBOX.MSG.m-001.high");
    }

    #[tokio::test]
    async fn test_subscribe_queue_group() {
        let mock = Arc::new(MockTransport::new());
        let arc = mock.clone();
        let client = MQ9Client { transport: mock };

        let _sub = client
            .subscribe("task.queue", |_msg| async {}, None, "workers")
            .await
            .unwrap();

        let calls = arc.subscribed();
        assert_eq!(calls[0].1.as_deref(), Some("workers"));
    }

    #[tokio::test]
    async fn test_subscribe_callback_invoked() {
        let mock = MockTransport::new();
        // Pre-load a message into the subscribe stream
        let payload_b64 = b64_encode(b"hello");
        let envelope = json!({
            "msg_id": "x1",
            "priority": "normal",
            "payload": payload_b64,
        });
        mock.push_sub_msg(
            "$mq9.AI.MAILBOX.MSG.m-001.normal",
            serde_json::to_vec(&envelope).unwrap(),
        );
        let client = make_client(mock);

        let received = Arc::new(Mutex::new(Vec::<Message>::new()));
        let received2 = received.clone();

        let _sub = client
            .subscribe(
                "m-001",
                move |msg| {
                    let r = received2.clone();
                    async move {
                        r.lock().unwrap().push(msg);
                    }
                },
                Some(Priority::Normal),
                "",
            )
            .await
            .unwrap();

        // Give the spawned task time to process
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;

        let msgs = received.lock().unwrap();
        assert_eq!(msgs.len(), 1);
        assert_eq!(msgs[0].msg_id, "x1");
        assert_eq!(msgs[0].payload, b"hello");
        assert_eq!(msgs[0].priority, Priority::Normal);
    }

    fn b64_encode(data: &[u8]) -> String {
        const ALPHA: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        let mut out = String::new();
        for chunk in data.chunks(3) {
            let b0 = chunk[0] as u32;
            let b1 = chunk.get(1).copied().unwrap_or(0) as u32;
            let b2 = chunk.get(2).copied().unwrap_or(0) as u32;
            let n = (b0 << 16) | (b1 << 8) | b2;
            out.push(ALPHA[((n >> 18) & 63) as usize] as char);
            out.push(ALPHA[((n >> 12) & 63) as usize] as char);
            out.push(if chunk.len() > 1 {
                ALPHA[((n >> 6) & 63) as usize] as char
            } else {
                '='
            });
            out.push(if chunk.len() > 2 {
                ALPHA[(n & 63) as usize] as char
            } else {
                '='
            });
        }
        out
    }

    #[tokio::test]
    async fn test_list_messages() {
        let mock = MockTransport::new();
        mock.push_ok(json!({
            "mail_id": "m-001",
            "messages": [
                { "msg_id": "msg-1", "priority": "high", "ts": 1000_i64 }
            ]
        }));
        let client = make_client(mock);

        let messages = client.list("m-001").await.unwrap();

        assert_eq!(messages.len(), 1);
        assert_eq!(messages[0].msg_id, "msg-1");
        assert_eq!(messages[0].priority, Priority::High);
        assert_eq!(messages[0].ts, 1000);
    }

    #[tokio::test]
    async fn test_list_request_subject() {
        let mock = Arc::new(MockTransport::new());
        mock.push_ok(json!({ "mail_id": "m-001", "messages": [] }));
        let arc = mock.clone();
        let client = MQ9Client { transport: mock };

        client.list("m-001").await.unwrap();

        assert_eq!(arc.requested()[0].0, "$mq9.AI.MAILBOX.LIST.m-001");
    }

    #[tokio::test]
    async fn test_list_empty_mailbox() {
        let mock = MockTransport::new();
        mock.push_ok(json!({ "mail_id": "m-001", "messages": [] }));
        let client = make_client(mock);

        let messages = client.list("m-001").await.unwrap();
        assert!(messages.is_empty());
    }

    #[tokio::test]
    async fn test_list_server_error() {
        let mock = MockTransport::new();
        mock.push_err("not found", 404);
        let client = make_client(mock);

        let result = client.list("m-999").await;
        assert!(result.is_err());
        assert_eq!(result.unwrap_err().code, 404);
    }

    // ------------------------------------------------------------------
    // delete
    // ------------------------------------------------------------------

    #[tokio::test]
    async fn test_delete_message() {
        let mock = Arc::new(MockTransport::new());
        mock.push_ok(json!({ "ok": true }));
        let arc = mock.clone();
        let client = MQ9Client { transport: mock };

        client.delete("m-001", "msg-42").await.unwrap();

        let calls = arc.requested();
        assert_eq!(calls[0].0, "$mq9.AI.MAILBOX.DELETE.m-001.msg-42");
    }

    #[tokio::test]
    async fn test_delete_server_error() {
        let mock = MockTransport::new();
        mock.push_err("message not found", 404);
        let client = make_client(mock);

        let result = client.delete("m-001", "bad-id").await;
        assert!(result.is_err());
        assert_eq!(result.unwrap_err().code, 404);
    }

    // ------------------------------------------------------------------
    // close (drain)
    // ------------------------------------------------------------------

    #[tokio::test]
    async fn test_close_calls_drain() {
        // drain() on MockTransport always returns Ok(()); just ensure no panic.
        let mock = MockTransport::new();
        let client = make_client(mock);
        client.close().await.unwrap();
    }

    // ------------------------------------------------------------------
    // MQ9Error
    // ------------------------------------------------------------------

    #[test]
    fn test_mq9_error_display_with_code() {
        let err = MQ9Error {
            message: "quota exceeded".into(),
            code: 429,
        };
        let s = err.to_string();
        assert!(s.contains("429"));
        assert!(s.contains("quota exceeded"));
    }

    #[test]
    fn test_mq9_error_display_no_code() {
        let err = MQ9Error {
            message: "connection failed".into(),
            code: 0,
        };
        let s = err.to_string();
        assert!(s.contains("connection failed"));
    }

    #[test]
    fn test_mq9_error_is_std_error() {
        let err: Box<dyn std::error::Error> = Box::new(MQ9Error {
            message: "oops".into(),
            code: 500,
        });
        assert!(err.to_string().contains("oops"));
    }

    // ------------------------------------------------------------------
    // Priority
    // ------------------------------------------------------------------

    #[test]
    fn test_priority_as_str() {
        assert_eq!(Priority::Critical.as_str(), "critical");
        assert_eq!(Priority::Urgent.as_str(), "urgent");
        assert_eq!(Priority::Normal.as_str(), "normal");
    }

    #[test]
    fn test_priority_from_str_lossy() {
        assert_eq!(Priority::from_str_lossy("critical"), Priority::Critical);
        assert_eq!(Priority::from_str_lossy("urgent"), Priority::Urgent);
        assert_eq!(Priority::from_str_lossy("normal"), Priority::Normal);
        assert_eq!(Priority::from_str_lossy("unknown"), Priority::Normal);
        assert_eq!(Priority::from_str_lossy("*"), Priority::Normal);
    }

    #[test]
    fn test_priority_display() {
        assert_eq!(format!("{}", Priority::Critical), "critical");
        assert_eq!(format!("{}", Priority::Urgent), "urgent");
        assert_eq!(format!("{}", Priority::Normal), "normal");
    }

    // ------------------------------------------------------------------
    // b64_decode helper
    // ------------------------------------------------------------------

    #[test]
    fn test_b64_decode_hello() {
        // "hello" in base64 is "aGVsbG8="
        assert_eq!(b64_decode("aGVsbG8=").unwrap(), b"hello");
    }

    #[test]
    fn test_b64_decode_empty() {
        assert_eq!(b64_decode("").unwrap(), b"");
    }

    #[test]
    fn test_b64_decode_invalid() {
        assert!(b64_decode("!!!").is_err());
    }

    #[test]
    fn test_b64_decode_no_padding() {
        // "hello" without padding
        assert_eq!(b64_decode("aGVsbG8").unwrap(), b"hello");
    }

    // ------------------------------------------------------------------
    // Subject helpers
    // ------------------------------------------------------------------

    #[test]
    fn test_subject_msg_normal() {
        assert_eq!(
            subject_msg("m-001", Priority::Normal),
            "$mq9.AI.MAILBOX.MSG.m-001"
        );
    }

    #[test]
    fn test_subject_msg_urgent() {
        assert_eq!(
            subject_msg("m-001", Priority::Urgent),
            "$mq9.AI.MAILBOX.MSG.m-001.urgent"
        );
    }

    #[test]
    fn test_subject_msg_critical() {
        assert_eq!(
            subject_msg("m-001", Priority::Critical),
            "$mq9.AI.MAILBOX.MSG.m-001.critical"
        );
    }

    #[test]
    fn test_subject_sub_wildcard() {
        assert_eq!(
            subject_sub("task.queue", "*"),
            "$mq9.AI.MAILBOX.MSG.task.queue.*"
        );
    }

    #[test]
    fn test_subject_list() {
        assert_eq!(subject_list("m-001"), "$mq9.AI.MAILBOX.LIST.m-001");
    }

    #[test]
    fn test_subject_delete() {
        assert_eq!(
            subject_delete("m-001", "msg-42"),
            "$mq9.AI.MAILBOX.DELETE.m-001.msg-42"
        );
    }

    // ------------------------------------------------------------------
    // parse_message_meta
    // ------------------------------------------------------------------

    #[test]
    fn test_parse_message_meta_ok() {
        let v = json!({ "msg_id": "x9", "priority": "high", "ts": 100_i64 });
        let meta = parse_message_meta(&v).unwrap();
        assert_eq!(meta.msg_id, "x9");
        assert_eq!(meta.priority, Priority::High);
        assert_eq!(meta.ts, 100);
    }

    #[test]
    fn test_parse_message_meta_missing_msg_id_returns_none() {
        let v = json!({ "priority": "low" });
        assert!(parse_message_meta(&v).is_none());
    }

    // ------------------------------------------------------------------
    // parse_incoming
    // ------------------------------------------------------------------

    fn make_raw_msg(subject: &str, payload: Vec<u8>) -> RawMsg {
        RawMsg {
            subject: subject.to_string(),
            payload: Bytes::from(payload),
        }
    }

    #[test]
    fn test_parse_incoming_json_envelope() {
        let envelope = json!({
            "msg_id": "x9",
            "priority": "high",
            "payload": b64_encode(b"data"),
        });
        let raw = make_raw_msg(
            "$mq9.AI.MAILBOX.MSG.m-001.high",
            serde_json::to_vec(&envelope).unwrap(),
        );
        let msg = parse_incoming("m-001", &raw);
        assert_eq!(msg.msg_id, "x9");
        assert_eq!(msg.priority, Priority::High);
        assert_eq!(msg.payload, b"data");
    }

    #[test]
    fn test_parse_incoming_raw_bytes_fallback() {
        let raw = make_raw_msg("$mq9.AI.MAILBOX.MSG.m-001.low", b"plain bytes".to_vec());
        let msg = parse_incoming("m-001", &raw);
        assert_eq!(msg.payload, b"plain bytes");
        assert_eq!(msg.priority, Priority::Low);
        assert_eq!(msg.msg_id, "");
    }

    #[test]
    fn test_parse_incoming_unknown_priority_defaults_to_normal() {
        let raw = make_raw_msg("$mq9.AI.MAILBOX.MSG.m-001.unknown", b"data".to_vec());
        let msg = parse_incoming("m-001", &raw);
        assert_eq!(msg.priority, Priority::Normal);
    }
}
