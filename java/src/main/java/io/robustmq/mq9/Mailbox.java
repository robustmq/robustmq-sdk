package io.robustmq.mq9;

public class Mailbox {
    private final String mailId;
    private final boolean isPublic;
    private final String name;
    private final String desc;

    public Mailbox(String mailId, boolean isPublic, String name, String desc) {
        this.mailId = mailId;
        this.isPublic = isPublic;
        this.name = name;
        this.desc = desc;
    }

    public String getMailId()   { return mailId; }
    public boolean isPublic()   { return isPublic; }
    public String getName()     { return name; }
    public String getDesc()     { return desc; }

    @Override
    public String toString() {
        return "Mailbox{mailId='" + mailId + "', public=" + isPublic + ", name='" + name + "'}";
    }
}
