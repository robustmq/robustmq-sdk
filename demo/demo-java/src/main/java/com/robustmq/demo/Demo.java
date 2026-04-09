package com.robustmq.demo;

import com.robustmq.mq9.Mailbox;
import com.robustmq.mq9.MQ9Client;
import com.robustmq.mq9.MessageMeta;
import com.robustmq.mq9.Priority;

import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * mq9 Java demo — connects to nats://demo.robustmq.com:4222 and runs the full scenario.
 *
 * Run:
 *   cd demo/demo-java
 *   mvn compile exec:java
 */
public class Demo {
    public static void main(String[] args) throws Exception {
        // demo.robustmq.com 是公共的 RobustMQ 服务，可用于验证功能和测试，也可修改为自己的服务地址。
        MQ9Client client = new MQ9Client("nats://demo.robustmq.com:4222");
        client.connect();
        System.out.println("[java] connected");

        // 1. Create a private mailbox (TTL 60s)
        Mailbox mailbox = client.create(60).get();
        System.out.println("[java] private mailbox: " + mailbox.getMailId());

        // 2. Send 3 messages with different priorities
        client.send(mailbox.getMailId(), "urgent task".getBytes(), Priority.HIGH).get();
        client.send(mailbox.getMailId(), "normal task".getBytes(), Priority.NORMAL).get();
        client.send(mailbox.getMailId(), "background task".getBytes(), Priority.LOW).get();
        System.out.println("[java] sent 3 messages (high / normal / low)");

        // 3. Subscribe and print received messages
        var dispatcher = client.subscribe(mailbox.getMailId(), msg ->
                System.out.printf("[java] received [%s] %s%n",
                        msg.getPriority().getValue(),
                        new String(msg.getPayload())),
                null, "").get();
        TimeUnit.MILLISECONDS.sleep(500);
        dispatcher.unsubscribe(null);

        // 4. List mailbox metadata
        List<MessageMeta> metas = client.list(mailbox.getMailId()).get();
        System.out.printf("[java] list: %d message(s) in mailbox%n", metas.size());
        for (MessageMeta m : metas) {
            System.out.printf("  msg_id=%s  priority=%s  ts=%d%n",
                    m.getMsgId(), m.getPriority().getValue(), m.getTs());
        }

        // 5. Delete first message
        if (!metas.isEmpty()) {
            client.delete(mailbox.getMailId(), metas.get(0).getMsgId()).get();
            System.out.println("[java] deleted " + metas.get(0).getMsgId());
        }

        // 6. Create a public mailbox
        Mailbox pub = client.createPublic(60, "demo.queue", "Demo queue").get();
        System.out.println("[java] public mailbox: " + pub.getMailId());

        client.close();
        System.out.println("[java] done");
    }
}
