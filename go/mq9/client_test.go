package mq9

import (
	"encoding/json"
	"fmt"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
)

// ---------------------------------------------------------------------------
// Mock NATSConn
// ---------------------------------------------------------------------------

type mockConn struct {
	// requestFn is called on each Request; if nil, returns an error
	requestFn func(subject string, data []byte) ([]byte, error)
	published []publishedMsg
}

type publishedMsg struct {
	Subject string
	Data    []byte
}

func (m *mockConn) Publish(subject string, data []byte) error {
	m.published = append(m.published, publishedMsg{subject, data})
	return nil
}

func (m *mockConn) Request(subject string, data []byte, _ time.Duration) (*nats.Msg, error) {
	if m.requestFn == nil {
		return nil, fmt.Errorf("no responder")
	}
	resp, err := m.requestFn(subject, data)
	if err != nil {
		return nil, err
	}
	return &nats.Msg{Data: resp}, nil
}

func (m *mockConn) Subscribe(_ string, _ nats.MsgHandler) (*nats.Subscription, error) {
	return &nats.Subscription{}, nil
}

func (m *mockConn) QueueSubscribe(_ string, _ string, _ nats.MsgHandler) (*nats.Subscription, error) {
	return &nats.Subscription{}, nil
}

func (m *mockConn) Drain() error { return nil }

// jsonReply marshals v and returns it as a NATS reply.
func jsonReply(v any) ([]byte, error) {
	return json.Marshal(v)
}

// newClient returns a client with the mock injected.
func newClient(mock *mockConn) *MQ9Client {
	return &MQ9Client{
		server:  "nats://localhost:4222",
		timeout: 5 * time.Second,
		nc:      mock,
	}
}

// ---------------------------------------------------------------------------
// Tests — Create
// ---------------------------------------------------------------------------

func TestCreate_Private(t *testing.T) {
	mock := &mockConn{requestFn: func(subject string, _ []byte) ([]byte, error) {
		if subject != subjectCreate {
			t.Errorf("unexpected subject %q", subject)
		}
		return jsonReply(map[string]any{"mail_id": "m-001"})
	}}

	c := newClient(mock)
	mb, err := c.Create(3600)
	if err != nil {
		t.Fatal(err)
	}
	if mb.MailID != "m-001" {
		t.Errorf("got mail_id %q, want %q", mb.MailID, "m-001")
	}
	if mb.Public {
		t.Error("expected private mailbox")
	}
}

func TestCreate_Public(t *testing.T) {
	mock := &mockConn{requestFn: func(_ string, data []byte) ([]byte, error) {
		var req map[string]any
		_ = json.Unmarshal(data, &req)
		if req["public"] != true {
			t.Error("expected public=true in request")
		}
		if req["name"] != "task.queue" {
			t.Errorf("expected name=task.queue, got %v", req["name"])
		}
		return jsonReply(map[string]any{"mail_id": "task.queue"})
	}}

	c := newClient(mock)
	mb, err := c.Create(86400, WithPublic("task.queue", "Tasks"))
	if err != nil {
		t.Fatal(err)
	}
	if mb.MailID != "task.queue" {
		t.Errorf("got %q, want %q", mb.MailID, "task.queue")
	}
	if !mb.Public {
		t.Error("expected public mailbox")
	}
}

func TestCreate_PublicWithoutName(t *testing.T) {
	c := newClient(&mockConn{})
	_, err := c.Create(3600, WithPublic("", ""))
	if err == nil {
		t.Fatal("expected error when name is empty")
	}
}

func TestCreate_ServerError(t *testing.T) {
	mock := &mockConn{requestFn: func(_ string, _ []byte) ([]byte, error) {
		return jsonReply(map[string]any{"error": "quota exceeded", "code": 429})
	}}
	c := newClient(mock)
	_, err := c.Create(3600)
	mq9Err, ok := err.(*MQ9Error)
	if !ok {
		t.Fatalf("expected *MQ9Error, got %T: %v", err, err)
	}
	if mq9Err.Code != 429 {
		t.Errorf("got code %d, want 429", mq9Err.Code)
	}
}

// ---------------------------------------------------------------------------
// Tests — Send
// ---------------------------------------------------------------------------

func TestSend_NormalPriority(t *testing.T) {
	mock := &mockConn{}
	c := newClient(mock)

	if err := c.Send("m-001", []byte("hello"), Normal); err != nil {
		t.Fatal(err)
	}
	if len(mock.published) != 1 {
		t.Fatalf("expected 1 publish, got %d", len(mock.published))
	}
	want := "$mq9.AI.MAILBOX.MSG.m-001.normal"
	if mock.published[0].Subject != want {
		t.Errorf("got subject %q, want %q", mock.published[0].Subject, want)
	}
}

func TestSend_HighPriority(t *testing.T) {
	mock := &mockConn{}
	c := newClient(mock)
	_ = c.Send("m-001", []byte("urgent"), High)
	want := "$mq9.AI.MAILBOX.MSG.m-001.high"
	if mock.published[0].Subject != want {
		t.Errorf("got %q, want %q", mock.published[0].Subject, want)
	}
}

// ---------------------------------------------------------------------------
// Tests — List
// ---------------------------------------------------------------------------

func TestList_Messages(t *testing.T) {
	mock := &mockConn{requestFn: func(subject string, _ []byte) ([]byte, error) {
		if subject != subjectList("m-001") {
			t.Errorf("unexpected subject %q", subject)
		}
		return jsonReply(map[string]any{
			"mail_id": "m-001",
			"messages": []any{
				map[string]any{
					"msg_id":   "x1",
					"priority": "high",
					"ts":       float64(100),
				},
			},
		})
	}}

	c := newClient(mock)
	msgs, err := c.List("m-001")
	if err != nil {
		t.Fatal(err)
	}
	if len(msgs) != 1 {
		t.Fatalf("expected 1 message, got %d", len(msgs))
	}
	if msgs[0].MsgID != "x1" {
		t.Errorf("got msg_id %q, want %q", msgs[0].MsgID, "x1")
	}
	if msgs[0].Priority != High {
		t.Errorf("got priority %q, want High", msgs[0].Priority)
	}
	if msgs[0].Ts != 100 {
		t.Errorf("got ts %d, want 100", msgs[0].Ts)
	}
}

func TestList_Empty(t *testing.T) {
	mock := &mockConn{requestFn: func(_ string, _ []byte) ([]byte, error) {
		return jsonReply(map[string]any{"mail_id": "m-001", "messages": []any{}})
	}}
	c := newClient(mock)
	msgs, err := c.List("m-001")
	if err != nil {
		t.Fatal(err)
	}
	if len(msgs) != 0 {
		t.Errorf("expected empty list, got %d", len(msgs))
	}
}

// ---------------------------------------------------------------------------
// Tests — Delete
// ---------------------------------------------------------------------------

func TestDelete(t *testing.T) {
	var calledSubject string
	mock := &mockConn{requestFn: func(subject string, _ []byte) ([]byte, error) {
		calledSubject = subject
		return jsonReply(map[string]any{"ok": true})
	}}
	c := newClient(mock)
	if err := c.Delete("m-001", "msg-42"); err != nil {
		t.Fatal(err)
	}
	want := "$mq9.AI.MAILBOX.DELETE.m-001.msg-42"
	if calledSubject != want {
		t.Errorf("got subject %q, want %q", calledSubject, want)
	}
}

// ---------------------------------------------------------------------------
// Tests — Not connected
// ---------------------------------------------------------------------------

func TestNotConnected(t *testing.T) {
	c := NewMQ9Client("nats://localhost:4222")
	_, err := c.List("m-001")
	if err == nil {
		t.Fatal("expected error when not connected")
	}
}

// ---------------------------------------------------------------------------
// Tests — Request timeout
// ---------------------------------------------------------------------------

func TestRequestTimeout(t *testing.T) {
	mock := &mockConn{requestFn: func(_ string, _ []byte) ([]byte, error) {
		return nil, fmt.Errorf("nats: timeout")
	}}
	c := newClient(mock)
	_, err := c.List("m-001")
	if err == nil {
		t.Fatal("expected error on timeout")
	}
}
