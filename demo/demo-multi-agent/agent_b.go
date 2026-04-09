// Agent B (Go) — subscribes to the rendezvous mailbox, reads Agent A's reply
// address and task messages, processes each task, and sends results back.
//
// Run order: start this process first, then run agent_a.py.
//
// Run:
//
//	cd demo/demo-multi-agent
//	go run agent_b.go
package main

import (
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/robustmq/robustmq-sdk/go/mq9"
)

const (
	// demo.robustmq.com is a public RobustMQ service for testing. Replace with your own server address if needed.
	server     = "nats://demo.robustmq.com:4222"
	rendezvous = "demo.multi-agent.rendezvous"
)

func main() {
	c := mq9.NewMQ9Client(server)
	if err := c.Connect(); err != nil {
		fmt.Fprintln(os.Stderr, "[agent-b] connect error:", err)
		os.Exit(1)
	}
	defer c.Close()
	fmt.Println("[agent-b] connected, waiting for messages on", rendezvous)

	var replyTo string   // Agent A's private mail_id, received as first message
	processed := 0
	expected := 3        // one reply address + 3 tasks; first message is the address

	done := make(chan struct{})

	sub, err := c.Subscribe(rendezvous, func(msg *mq9.Message) {
		text := string(msg.Payload)

		// First message is Agent A's reply address (not a task)
		if replyTo == "" {
			replyTo = strings.TrimSpace(text)
			fmt.Printf("[agent-b] discovered Agent A reply address: %s\n", replyTo)
			return
		}

		// Process task
		fmt.Printf("[agent-b] processing [%s]: %s\n", msg.Priority, text)
		time.Sleep(100 * time.Millisecond) // simulate work

		result := fmt.Sprintf("DONE: %s", text)

		// Send result back to Agent A
		if err := c.Send(replyTo, []byte(result), mq9.Normal); err != nil {
			fmt.Fprintln(os.Stderr, "[agent-b] send error:", err)
			return
		}
		fmt.Printf("[agent-b] sent result to %s: %s\n", replyTo, result)

		processed++
		if processed >= expected {
			close(done)
		}
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, "[agent-b] subscribe error:", err)
		os.Exit(1)
	}

	// Wait for all tasks to be processed (or timeout after 30 s)
	select {
	case <-done:
		fmt.Printf("[agent-b] done — processed %d tasks\n", processed)
	case <-time.After(30 * time.Second):
		fmt.Printf("[agent-b] timeout — processed %d/%d tasks\n", processed, expected)
	}

	sub.Unsubscribe()
}
