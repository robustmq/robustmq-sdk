package com.robustmq.mq9;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.nats.client.Connection;
import io.nats.client.Dispatcher;
import io.nats.client.Message;
import io.nats.client.Nats;
import io.nats.client.Options;

import java.io.IOException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.concurrent.CompletableFuture;

/**
 * Async mq9 client for RobustMQ.
 *
 * <pre>{@code
 * MQ9Client client = new MQ9Client("nats://localhost:4222");
 * client.connect();
 *
 * Mailbox mailbox = client.create(3600).get();
 * client.send(mailbox.getMailId(), "hello".getBytes(), Priority.NORMAL).get();
 *
 * client.subscribe(mailbox.getMailId(), msg ->
 *     System.out.println(new String(msg.getPayload())),
 *     null, "").get();
 *
 * client.close();
 * }</pre>
 */
public class MQ9Client implements AutoCloseable {

    private static final String PREFIX = "$mq9.AI";
    private static final String MAILBOX_CREATE = PREFIX + ".MAILBOX.CREATE";
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(5);

    private final String server;
    private final ObjectMapper mapper = new ObjectMapper();
    // Package-private for testing: allows injecting a mock Connection
    Connection nc;

    public MQ9Client(String server) {
        this.server = server;
    }

    // ── Connection ────────────────────────────────────────────────────────────

    public void connect() throws MQ9Error {
        try {
            Options opts = new Options.Builder()
                    .server(server)
                    .maxReconnects(-1)
                    .build();
            nc = Nats.connect(opts);
        } catch (IOException | InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new MQ9Error("connection failed: " + e.getMessage());
        }
    }

    @Override
    public void close() {
        if (nc != null) {
            try {
                nc.drain(Duration.ofSeconds(5)).get();
            } catch (Exception e) {
                // best-effort drain
            }
        }
    }

    // ── Create ────────────────────────────────────────────────────────────────

    public CompletableFuture<com.robustmq.mq9.Mailbox> create(int ttl) {
        return createInternal(ttl, false, "", "");
    }

    public CompletableFuture<com.robustmq.mq9.Mailbox> createPublic(int ttl, String name, String desc) {
        if (name == null || name.isEmpty()) {
            return CompletableFuture.failedFuture(new MQ9Error("name is required when public=true"));
        }
        return createInternal(ttl, true, name, desc != null ? desc : "");
    }

    private CompletableFuture<com.robustmq.mq9.Mailbox> createInternal(int ttl, boolean isPublic,
                                                                        String name, String desc) {
        return CompletableFuture.supplyAsync(() -> {
            ObjectNode req = mapper.createObjectNode();
            req.put("ttl", ttl);
            if (isPublic) {
                req.put("public", true);
                req.put("name", name);
                if (!desc.isEmpty()) req.put("desc", desc);
            }
            JsonNode resp = doRequest(MAILBOX_CREATE, req);
            String mailId = resp.get("mail_id").asText();
            return new com.robustmq.mq9.Mailbox(mailId, isPublic, name, desc);
        });
    }

    // ── Send ──────────────────────────────────────────────────────────────────

    public CompletableFuture<Void> send(String mailId, byte[] payload, Priority priority) {
        return CompletableFuture.runAsync(() -> {
            ensureConnected();
            String subject = PREFIX + ".MAILBOX.MSG." + mailId + "." + priority.getValue();
            try {
                nc.publish(subject, payload);
            } catch (Exception e) {
                throw new RuntimeException(new MQ9Error("publish failed: " + e.getMessage()));
            }
        });
    }

    // ── Subscribe ─────────────────────────────────────────────────────────────

    public CompletableFuture<Dispatcher> subscribe(String mailId, MessageHandler handler,
                                                    Priority priority, String queueGroup) {
        return CompletableFuture.supplyAsync(() -> {
            ensureConnected();
            String sub = (priority != null)
                    ? PREFIX + ".MAILBOX.MSG." + mailId + "." + priority.getValue()
                    : PREFIX + ".MAILBOX.MSG." + mailId + ".*";

            Dispatcher dispatcher = nc.createDispatcher((Message msg) -> {
                com.robustmq.mq9.Message m = parseIncoming(mailId, msg);
                handler.onMessage(m);
            });

            if (queueGroup != null && !queueGroup.isEmpty()) {
                dispatcher.subscribe(sub, queueGroup);
            } else {
                dispatcher.subscribe(sub);
            }
            return dispatcher;
        });
    }

    // ── List ──────────────────────────────────────────────────────────────────

    public CompletableFuture<List<MessageMeta>> list(String mailId) {
        return CompletableFuture.supplyAsync(() -> {
            String subject = PREFIX + ".MAILBOX.LIST." + mailId;
            JsonNode resp = doRequest(subject, mapper.createObjectNode());
            List<MessageMeta> metas = new ArrayList<>();
            JsonNode arr = resp.get("messages");
            if (arr != null && arr.isArray()) {
                for (JsonNode node : arr) {
                    metas.add(new MessageMeta(
                            node.path("msg_id").asText(""),
                            Priority.fromString(node.path("priority").asText("normal")),
                            node.path("ts").asLong(0)
                    ));
                }
            }
            return metas;
        });
    }

    // ── Delete ────────────────────────────────────────────────────────────────

    public CompletableFuture<Void> delete(String mailId, String msgId) {
        return CompletableFuture.runAsync(() -> {
            String subject = PREFIX + ".MAILBOX.DELETE." + mailId + "." + msgId;
            doRequest(subject, mapper.createObjectNode());
        });
    }

    // ── Internal helpers ─────────────────────────────────────────────────────

    private void ensureConnected() {
        if (nc == null) {
            throw new IllegalStateException("Not connected. Call connect() first.");
        }
    }

    private JsonNode doRequest(String subject, ObjectNode payload) {
        ensureConnected();
        try {
            byte[] data = mapper.writeValueAsBytes(payload);
            io.nats.client.Message reply = nc.request(subject, data, REQUEST_TIMEOUT);
            if (reply == null) {
                throw new RuntimeException(new MQ9Error("request timed out: " + subject));
            }
            JsonNode resp = mapper.readTree(reply.getData());
            if (resp.has("error")) {
                int code = resp.path("code").asInt(0);
                throw new RuntimeException(new MQ9Error(resp.get("error").asText(), code));
            }
            return resp;
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException(new MQ9Error("request failed: " + e.getMessage()));
        }
    }

    private com.robustmq.mq9.Message parseIncoming(String mailId, Message raw) {
        // Extract priority from subject last token
        String subject = raw.getSubject();
        String[] parts = subject.split("\\.");
        String priorityStr = parts.length > 0 ? parts[parts.length - 1] : "normal";
        Priority priority = Priority.fromString(priorityStr);

        // Try JSON envelope first
        try {
            JsonNode node = mapper.readTree(raw.getData());
            if (node.has("msg_id")) {
                return parseMessageNode(mailId, node);
            }
        } catch (Exception ignored) {
            // fall through to raw payload
        }

        return new com.robustmq.mq9.Message("", mailId, priority, raw.getData());
    }

    private com.robustmq.mq9.Message parseMessageNode(String mailId, JsonNode node) {
        String msgId = node.path("msg_id").asText("");
        Priority priority = Priority.fromString(node.path("priority").asText("normal"));
        String rawPayload = node.path("payload").asText("");
        byte[] payload = rawPayload.isEmpty() ? new byte[0] : Base64.getDecoder().decode(rawPayload);
        return new com.robustmq.mq9.Message(msgId, mailId, priority, payload);
    }
}
