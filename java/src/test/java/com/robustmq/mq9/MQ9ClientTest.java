package com.robustmq.mq9;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.nats.client.Connection;
import io.nats.client.Dispatcher;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutionException;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class MQ9ClientTest {

    @Mock
    private Connection mockNc;

    private MQ9Client client;
    private final ObjectMapper mapper = new ObjectMapper();

    @BeforeEach
    void setUp() {
        client = new MQ9Client("nats://localhost:4222");
        client.nc = mockNc;
    }

    // ── helpers ──────────────────────────────────────────────────────────────

    /** Returns a stub NATS message carrying the given JSON bytes. */
    private io.nats.client.Message fakeReply(String json) {
        return new FakeNatsMessage(json.getBytes(StandardCharsets.UTF_8));
    }

    // ── create ────────────────────────────────────────────────────────────────

    @Test
    void createPrivateMailbox() throws Exception {
        when(mockNc.request(eq("$mq9.AI.MAILBOX.CREATE"), any(byte[].class), any(Duration.class)))
                .thenReturn(fakeReply("{\"mail_id\":\"m-001\"}"));

        Mailbox mailbox = client.create(3600).get();

        assertEquals("m-001", mailbox.getMailId());
        assertFalse(mailbox.isPublic());
    }

    @Test
    void createPublicMailbox() throws Exception {
        when(mockNc.request(eq("$mq9.AI.MAILBOX.CREATE"), any(byte[].class), any(Duration.class)))
                .thenReturn(fakeReply("{\"mail_id\":\"task.queue\"}"));

        Mailbox mailbox = client.createPublic(86400, "task.queue", "Task queue").get();

        assertEquals("task.queue", mailbox.getMailId());
        assertTrue(mailbox.isPublic());
        assertEquals("task.queue", mailbox.getName());
    }

    @Test
    void createPublicRequiresName() {
        ExecutionException ex = assertThrows(ExecutionException.class,
                () -> client.createPublic(3600, "", "").get());
        assertInstanceOf(MQ9Error.class, ex.getCause());
    }

    @Test
    void createServerError() throws Exception {
        when(mockNc.request(any(), any(byte[].class), any(Duration.class)))
                .thenReturn(fakeReply("{\"error\":\"quota exceeded\",\"code\":429}"));

        ExecutionException ex = assertThrows(ExecutionException.class,
                () -> client.create(3600).get());
        assertInstanceOf(RuntimeException.class, ex.getCause());
        assertTrue(ex.getCause().getCause() instanceof MQ9Error);
        assertEquals(429, ((MQ9Error) ex.getCause().getCause()).getCode());
    }

    // ── send ──────────────────────────────────────────────────────────────────

    @Test
    void sendNormalPriority() throws Exception {
        client.send("m-001", "hello".getBytes(), Priority.NORMAL).get();
        // normal uses bare subject (no suffix)
        verify(mockNc).publish("$mq9.AI.MAILBOX.MSG.m-001", "hello".getBytes());
    }

    @Test
    void sendCriticalPriority() throws Exception {
        client.send("m-001", "abort".getBytes(), Priority.CRITICAL).get();
        verify(mockNc).publish("$mq9.AI.MAILBOX.MSG.m-001.critical", "abort".getBytes());
    }

    @Test
    void sendUrgentPriority() throws Exception {
        client.send("m-001", "interrupt".getBytes(), Priority.URGENT).get();
        verify(mockNc).publish("$mq9.AI.MAILBOX.MSG.m-001.urgent", "interrupt".getBytes());
    }

    // ── list ──────────────────────────────────────────────────────────────────

    @Test
    void listMessages() throws Exception {
        String json = "{\"mail_id\":\"m-001\",\"messages\":[{\"msg_id\":\"x1\","
                + "\"priority\":\"critical\",\"ts\":100}]}";
        when(mockNc.request(eq("$mq9.AI.MAILBOX.LIST.m-001"), any(byte[].class), any(Duration.class)))
                .thenReturn(fakeReply(json));

        List<MessageMeta> metas = client.list("m-001").get();

        assertEquals(1, metas.size());
        assertEquals("x1", metas.get(0).getMsgId());
        assertEquals(Priority.CRITICAL, metas.get(0).getPriority());
        assertEquals(100L, metas.get(0).getTs());
    }

    @Test
    void listEmpty() throws Exception {
        when(mockNc.request(eq("$mq9.AI.MAILBOX.LIST.m-001"), any(byte[].class), any(Duration.class)))
                .thenReturn(fakeReply("{\"mail_id\":\"m-001\",\"messages\":[]}"));

        List<MessageMeta> metas = client.list("m-001").get();
        assertTrue(metas.isEmpty());
    }

    // ── delete ────────────────────────────────────────────────────────────────

    @Test
    void deleteMessage() throws Exception {
        when(mockNc.request(eq("$mq9.AI.MAILBOX.DELETE.m-001.msg-42"), any(byte[].class), any(Duration.class)))
                .thenReturn(fakeReply("{\"ok\":true}"));

        client.delete("m-001", "msg-42").get();

        verify(mockNc).request(eq("$mq9.AI.MAILBOX.DELETE.m-001.msg-42"), any(byte[].class), any(Duration.class));
    }

    // ── not connected ─────────────────────────────────────────────────────────

    @Test
    void notConnectedThrows() {
        MQ9Client disconnected = new MQ9Client("nats://localhost:4222");
        ExecutionException ex = assertThrows(ExecutionException.class,
                () -> disconnected.list("m-001").get());
        assertInstanceOf(RuntimeException.class, ex.getCause());
    }

    // ── subscribe ─────────────────────────────────────────────────────────────

    @Test
    void subscribeAllPriorities() throws Exception {
        Dispatcher dispatcher = mock(Dispatcher.class);
        when(dispatcher.subscribe(anyString())).thenReturn(dispatcher);
        when(mockNc.createDispatcher(any())).thenReturn(dispatcher);

        client.subscribe("m-001", msg -> {}, null, "").get();

        verify(dispatcher).subscribe("$mq9.AI.MAILBOX.MSG.m-001.*");
    }

    @Test
    void subscribeSinglePriority_Critical() throws Exception {
        Dispatcher dispatcher = mock(Dispatcher.class);
        when(dispatcher.subscribe(anyString())).thenReturn(dispatcher);
        when(mockNc.createDispatcher(any())).thenReturn(dispatcher);

        client.subscribe("m-001", msg -> {}, Priority.CRITICAL, "").get();

        verify(dispatcher).subscribe("$mq9.AI.MAILBOX.MSG.m-001.critical");
    }

    @Test
    void subscribeSinglePriority_Normal() throws Exception {
        Dispatcher dispatcher = mock(Dispatcher.class);
        when(dispatcher.subscribe(anyString())).thenReturn(dispatcher);
        when(mockNc.createDispatcher(any())).thenReturn(dispatcher);

        client.subscribe("m-001", msg -> {}, Priority.NORMAL, "").get();

        // normal uses bare subject (no suffix)
        verify(dispatcher).subscribe("$mq9.AI.MAILBOX.MSG.m-001");
    }

    @Test
    void subscribeQueueGroup() throws Exception {
        Dispatcher dispatcher = mock(Dispatcher.class);
        when(dispatcher.subscribe(anyString(), anyString())).thenReturn(dispatcher);
        when(mockNc.createDispatcher(any())).thenReturn(dispatcher);

        client.subscribe("m-001", msg -> {}, null, "workers").get();

        verify(dispatcher).subscribe("$mq9.AI.MAILBOX.MSG.m-001.*", "workers");
    }

    // ── close ─────────────────────────────────────────────────────────────────

    @Test
    void closeDrainsConnection() throws Exception {
        when(mockNc.drain(any(Duration.class)))
                .thenReturn(java.util.concurrent.CompletableFuture.completedFuture(true));

        assertDoesNotThrow(() -> client.close());

        verify(mockNc).drain(any(Duration.class));
    }

    // ── timeout ───────────────────────────────────────────────────────────────

    @Test
    void requestTimeoutThrows() throws Exception {
        when(mockNc.request(any(), any(byte[].class), any(Duration.class))).thenReturn(null);

        ExecutionException ex = assertThrows(ExecutionException.class,
                () -> client.list("m-001").get());
        assertTrue(ex.getCause().getCause() instanceof MQ9Error);
        assertTrue(ex.getCause().getCause().getMessage().contains("timed out"));
    }
}
