# Go SDK

**Module:** `github.com/robustmq/robustmq-sdk-go/mq9`  
**Requires:** Go 1.21+, `nats.go`

## Install

```bash
go get github.com/robustmq/robustmq-sdk-go
```

## Quick start

```go
package main

import (
    "fmt"
    "time"
    "github.com/robustmq/robustmq-sdk-go/mq9"
)

func main() {
    c := mq9.NewMQ9Client("nats://localhost:4222")
    c.Connect()
    defer c.Close()

    // Create mailbox
    mailbox, _ := c.Create(3600)

    // Send
    c.Send(mailbox.MailID, []byte("hello"), mq9.Normal)

    // Subscribe
    sub, _ := c.Subscribe(mailbox.MailID, func(msg *mq9.Message) {
        fmt.Println(string(msg.Payload))
    })
    time.Sleep(200 * time.Millisecond)
    sub.Unsubscribe()

    // List metadata (no payload)
    metas, _ := c.List(mailbox.MailID)
    // metas[i].MsgID, .Priority, .Ts

    // Delete
    c.Delete(mailbox.MailID, metas[0].MsgID)
}
```

## API

```go
c := mq9.NewMQ9Client(server string) *MQ9Client

c.Connect() error
c.Close() error

c.Create(ttl int, opts ...CreateOption) (*Mailbox, error)
// Options: mq9.WithPublic(name, desc string)

c.Send(mailID string, payload []byte, priority Priority) error

c.Subscribe(mailID string, cb func(*Message), opts ...SubscribeOption) (*Subscription, error)
// Options: mq9.WithPriority(p), mq9.WithQueueGroup(group)

c.List(mailID string) ([]*MessageMeta, error)
// MessageMeta: MsgID, Priority, Ts

c.Delete(mailID, msgID string) error
```

## Priority

```go
mq9.High    // "high"
mq9.Normal  // "normal"
mq9.Low     // "low"
```

## Public mailbox

```go
mailbox, _ := c.Create(3600, mq9.WithPublic("task.queue", "Tasks"))
// mailbox.MailID == "task.queue"
```

## Queue group

```go
sub, _ := c.Subscribe(mailID, handler, mq9.WithQueueGroup("workers"))
```
