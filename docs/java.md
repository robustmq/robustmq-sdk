# Java SDK

**Package:** `io.robustmq.mq9`  
**Requires:** Java 17+, `jnats`, `jackson-databind`

## Install

```xml
<dependency>
  <groupId>io.robustmq</groupId>
  <artifactId>robustmq-sdk</artifactId>
  <version>1.0.0</version>
</dependency>
```

## Quick start

```java
import io.robustmq.mq9.*;
import java.util.List;

MQ9Client client = new MQ9Client("nats://localhost:4222");
client.connect();

// Create mailbox
Mailbox mailbox = client.create(3600).get();

// Send
client.send(mailbox.getMailId(), "hello".getBytes(), Priority.NORMAL).get();

// Subscribe
var dispatcher = client.subscribe(mailbox.getMailId(), msg ->
    System.out.println(new String(msg.getPayload())),
    null, "").get();

// List metadata (no payload)
List<MessageMeta> metas = client.list(mailbox.getMailId()).get();
// metas.get(i).getMsgId(), .getPriority(), .getTs()

// Delete
client.delete(mailbox.getMailId(), metas.get(0).getMsgId()).get();

dispatcher.unsubscribe(null);
client.close();
```

## API

```java
MQ9Client(String server)

void connect() throws MQ9Error
void close()                          // AutoCloseable

CompletableFuture<Mailbox> create(int ttl)
CompletableFuture<Mailbox> createPublic(int ttl, String name, String desc)

CompletableFuture<Void> send(String mailId, byte[] payload, Priority priority)

CompletableFuture<Dispatcher> subscribe(String mailId, MessageHandler handler,
                                         Priority priority,   // null = all
                                         String queueGroup)

CompletableFuture<List<MessageMeta>> list(String mailId)
// MessageMeta: getMsgId(), getPriority(), getTs()

CompletableFuture<Void> delete(String mailId, String msgId)
```

## Priority

```java
Priority.HIGH    // "high"
Priority.NORMAL  // "normal"
Priority.LOW     // "low"
```

## Public mailbox

```java
Mailbox pub = client.createPublic(3600, "task.queue", "Tasks").get();
// pub.getMailId() == "task.queue"
```

## Queue group

```java
client.subscribe(mailId, handler, null, "workers").get();
```
