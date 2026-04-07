package io.robustmq.mq9;

public class MQ9Error extends Exception {
    private final int code;

    public MQ9Error(String message, int code) {
        super(message);
        this.code = code;
    }

    public MQ9Error(String message) {
        this(message, 0);
    }

    public int getCode() {
        return code;
    }
}
