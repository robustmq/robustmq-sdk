# robustmq-go

Go SDK for [RobustMQ](https://github.com/robustmq/robustmq) — mq9 AI-native async messaging.

**Status: not yet implemented.** Directory structure and module file are scaffolded.

## Planned dependency

- [`nats.go`](https://github.com/nats-io/nats.go) — NATS client

## Planned API

```go
import "github.com/robustmq/robustmq-sdk-go/mq9"

client, _ := mq9.Connect("nats://localhost:4222")
defer client.Close()

mailbox, _ := client.Create(mq9.CreateOptions{TTL: 3600})
client.Send(mailbox.MailID, []byte("hello"), mq9.Normal)

client.Subscribe(mailbox.MailID, func(msg *mq9.Message) {
    fmt.Println(string(msg.Payload))
}, mq9.AnyPriority)
```

See [docs/mq9-protocol.md](../docs/mq9-protocol.md) for the full protocol reference.
