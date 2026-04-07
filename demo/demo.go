//go:build ignore

// mq9 Go demo — connects to nats://localhost:4222 and runs the full scenario.
//
// Run:
//
//	cd go && go run ../demo/demo.go

package main

import (
	"fmt"
	"os"
	"time"

	"github.com/robustmq/robustmq-sdk-go/mq9"
)

func main() {
	c := mq9.NewMQ9Client("nats://localhost:4222")
	if err := c.Connect(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer c.Close()
	fmt.Println("[go] connected")

	// 1. Create a private mailbox (TTL 60s)
	mailbox, err := c.Create(60)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Printf("[go] private mailbox: %s\n", mailbox.MailID)

	// 2. Send 3 messages with different priorities
	_ = c.Send(mailbox.MailID, []byte("urgent task"), mq9.High)
	_ = c.Send(mailbox.MailID, []byte("normal task"), mq9.Normal)
	_ = c.Send(mailbox.MailID, []byte("background task"), mq9.Low)
	fmt.Println("[go] sent 3 messages (high / normal / low)")

	// 3. Subscribe and print received messages
	sub, err := c.Subscribe(mailbox.MailID, func(msg *mq9.Message) {
		fmt.Printf("[go] received [%s] %s\n", msg.Priority, msg.Payload)
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	time.Sleep(500 * time.Millisecond)
	sub.Unsubscribe()

	// 4. List mailbox metadata
	metas, err := c.List(mailbox.MailID)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Printf("[go] list: %d message(s) in mailbox\n", len(metas))
	for _, m := range metas {
		fmt.Printf("  msg_id=%s  priority=%s  ts=%d\n", m.MsgID, m.Priority, m.Ts)
	}

	// 5. Delete first message
	if len(metas) > 0 {
		_ = c.Delete(mailbox.MailID, metas[0].MsgID)
		fmt.Printf("[go] deleted %s\n", metas[0].MsgID)
	}

	// 6. Create a public mailbox
	pub, err := c.Create(60, mq9.WithPublic("demo.queue", "Demo queue"))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Printf("[go] public mailbox: %s\n", pub.MailID)

	fmt.Println("[go] done")
}
