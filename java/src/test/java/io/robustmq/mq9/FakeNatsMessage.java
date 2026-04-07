package io.robustmq.mq9;

import io.nats.client.Connection;
import io.nats.client.Subscription;
import io.nats.client.impl.AckType;
import io.nats.client.impl.Headers;
import io.nats.client.impl.NatsJetStreamMetaData;
import io.nats.client.support.Status;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

/** Minimal NATS Message stub for unit tests. Only getData() is meaningful. */
class FakeNatsMessage implements io.nats.client.Message {
    private final byte[] data;

    FakeNatsMessage(byte[] data) { this.data = data; }

    @Override public byte[] getData() { return data; }
    @Override public String getSubject() { return "_INBOX.reply"; }
    @Override public String getReplyTo() { return null; }
    @Override public Headers getHeaders() { return null; }
    @Override public boolean hasHeaders() { return false; }
    @Override public Connection getConnection() { return null; }
    @Override public boolean isJetStream() { return false; }
    @Override public boolean isStatusMessage() { return false; }
    @Override public Status getStatus() { return null; }
    @Override public String getSID() { return null; }
    @Override public boolean isUtf8mode() { return false; }
    @Override public Subscription getSubscription() { return null; }
    @Override public AckType lastAck() { return null; }
    @Override public void ack() {}
    @Override public void ackSync(Duration d) throws TimeoutException, InterruptedException {}
    @Override public void nak() {}
    @Override public void nakWithDelay(Duration d) {}
    @Override public void nakWithDelay(long ms) {}
    @Override public void inProgress() {}
    @Override public void term() {}
    @Override public NatsJetStreamMetaData metaData() { return null; }
}
