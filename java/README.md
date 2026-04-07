# robustmq-java

Java SDK for [RobustMQ](https://github.com/robustmq/robustmq) — mq9 AI-native async messaging.

**Status: not yet implemented.** Directory structure and Maven POM are scaffolded.

## Planned dependencies

- [`jnats`](https://github.com/nats-io/nats.java) — NATS Java client
- `jackson-databind` — JSON serialization

## Planned API

```java
import io.robustmq.mq9.Client;

Client client = new Client("nats://localhost:4222");
client.connect();

Mailbox mailbox = client.create(3600);
client.send(mailbox.getMailId(), "hello".getBytes(), Priority.NORMAL);

client.subscribe(mailbox.getMailId(), msg -> {
    System.out.println(new String(msg.getPayload()));
});

client.close();
```

See [docs/mq9-protocol.md](../docs/mq9-protocol.md) for the full protocol reference.
