package io.robustmq.mq9;

public enum Priority {
    HIGH("high"),
    NORMAL("normal"),
    LOW("low");

    private final String value;

    Priority(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public static Priority fromString(String s) {
        for (Priority p : values()) {
            if (p.value.equalsIgnoreCase(s)) return p;
        }
        return NORMAL;
    }
}
