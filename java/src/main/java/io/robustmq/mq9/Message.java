package io.robustmq.mq9;

public class Message {
    private final String msgId;
    private final String mailId;
    private final Priority priority;
    private final byte[] payload;

    public Message(String msgId, String mailId, Priority priority, byte[] payload) {
        this.msgId = msgId;
        this.mailId = mailId;
        this.priority = priority;
        this.payload = payload;
    }

    public String getMsgId()      { return msgId; }
    public String getMailId()     { return mailId; }
    public Priority getPriority() { return priority; }
    public byte[] getPayload()    { return payload; }
}
