package com.robustmq.mq9;

@FunctionalInterface
public interface MessageHandler {
    void onMessage(Message message);
}
