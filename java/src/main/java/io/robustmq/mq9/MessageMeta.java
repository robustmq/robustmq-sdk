package io.robustmq.mq9;

public class MessageMeta {
    private final String msgId;
    private final Priority priority;
    private final long ts;

    public MessageMeta(String msgId, Priority priority, long ts) {
        this.msgId = msgId;
        this.priority = priority;
        this.ts = ts;
    }

    public String getMsgId()      { return msgId; }
    public Priority getPriority() { return priority; }
    public long getTs()           { return ts; }
}
