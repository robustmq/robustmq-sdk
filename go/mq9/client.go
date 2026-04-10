// Package mq9 provides a client for the mq9 AI-native async messaging protocol.
// Messages are durable: they persist until TTL expires, so senders and receivers
// do not need to be online simultaneously.
package mq9

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/nats-io/nats.go"
)

// ---------------------------------------------------------------------------
// Subject constants
// ---------------------------------------------------------------------------

const (
	prefix        = "$mq9.AI"
	subjectCreate = prefix + ".MAILBOX.CREATE"
)

func subjectMsgBase(mailID string) string {
	return fmt.Sprintf("%s.MAILBOX.MSG.%s", prefix, mailID)
}

// subjectMsg returns the send subject. Normal uses the bare subject; urgent/critical append a suffix.
func subjectMsg(mailID string, p Priority) string {
	if p == Normal {
		return subjectMsgBase(mailID)
	}
	return fmt.Sprintf("%s.%s", subjectMsgBase(mailID), string(p))
}

// subjectSub returns the subscribe subject. "*" uses the wildcard suffix.
func subjectSub(mailID, priority string) string {
	if priority == "*" {
		return subjectMsgBase(mailID) + ".*"
	}
	if Priority(priority) == Normal {
		return subjectMsgBase(mailID)
	}
	return fmt.Sprintf("%s.%s", subjectMsgBase(mailID), priority)
}
func subjectList(mailID string) string {
	return fmt.Sprintf("%s.MAILBOX.LIST.%s", prefix, mailID)
}
func subjectDelete(mailID, msgID string) string {
	return fmt.Sprintf("%s.MAILBOX.DELETE.%s.%s", prefix, mailID, msgID)
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// Priority is the message priority level.
type Priority string

const (
	Critical Priority = "critical"
	Urgent   Priority = "urgent"
	Normal   Priority = "normal"
)

// Mailbox represents a created mq9 mailbox.
type Mailbox struct {
	MailID string
	Public bool
	Name   string
	Desc   string
}

// MessageMeta is metadata for a message returned by List(). Does not include payload.
type MessageMeta struct {
	MsgID    string
	Priority Priority
	Ts       int64 // Unix timestamp of message creation
}

// Message is a full message received via Subscribe().
type Message struct {
	MsgID    string
	MailID   string
	Priority Priority
	Payload  []byte
}

// Subscription is an active mq9 subscription.
type Subscription struct {
	sub *nats.Subscription
}

// Unsubscribe cancels the subscription.
func (s *Subscription) Unsubscribe() error {
	return s.sub.Unsubscribe()
}

// MQ9Error is returned when the server sends an error response.
type MQ9Error struct {
	Msg  string
	Code int
}

func (e *MQ9Error) Error() string {
	if e.Code != 0 {
		return fmt.Sprintf("mq9 error (code %d): %s", e.Code, e.Msg)
	}
	return "mq9 error: " + e.Msg
}

// ---------------------------------------------------------------------------
// Functional options
// ---------------------------------------------------------------------------

// CreateOption configures mailbox creation.
type CreateOption func(*createOptions)

type createOptions struct {
	public bool
	name   string
	desc   string
}

// WithPublic marks the mailbox as publicly discoverable.
func WithPublic(name, desc string) CreateOption {
	return func(o *createOptions) {
		o.public = true
		o.name = name
		o.desc = desc
	}
}

// SubscribeOption configures a subscription.
type SubscribeOption func(*subscribeOptions)

type subscribeOptions struct {
	priority   string // "" means "*"
	queueGroup string
}

// WithPriority filters subscription to a single priority level.
func WithPriority(p Priority) SubscribeOption {
	return func(o *subscribeOptions) { o.priority = string(p) }
}

// WithQueueGroup sets the NATS queue group for competitive consumption.
func WithQueueGroup(group string) SubscribeOption {
	return func(o *subscribeOptions) { o.queueGroup = group }
}

// ---------------------------------------------------------------------------
// NATSConn interface — allows injecting a mock in tests
// ---------------------------------------------------------------------------

// NATSConn abstracts the nats.Conn operations used by MQ9Client.
type NATSConn interface {
	Publish(subject string, data []byte) error
	Request(subject string, data []byte, timeout time.Duration) (*nats.Msg, error)
	Subscribe(subject string, cb nats.MsgHandler) (*nats.Subscription, error)
	QueueSubscribe(subject, queue string, cb nats.MsgHandler) (*nats.Subscription, error)
	Drain() error
}

// ---------------------------------------------------------------------------
// MQ9Client
// ---------------------------------------------------------------------------

const defaultTimeout = 5 * time.Second

// MQ9Client is an async mq9 client for RobustMQ.
type MQ9Client struct {
	server  string
	timeout time.Duration
	nc      NATSConn
}

// NewMQ9Client creates a new client. Call Connect before using it.
func NewMQ9Client(server string) *MQ9Client {
	return &MQ9Client{server: server, timeout: defaultTimeout}
}

// Connect establishes a connection to the NATS server.
func (c *MQ9Client) Connect() error {
	nc, err := nats.Connect(c.server,
		nats.MaxReconnects(-1),
		nats.ReconnectWait(2*time.Second),
	)
	if err != nil {
		return fmt.Errorf("mq9: connect: %w", err)
	}
	c.nc = nc
	return nil
}

// Close drains and closes the connection.
func (c *MQ9Client) Close() error {
	if c.nc == nil {
		return nil
	}
	return c.nc.Drain()
}

// ---------------------------------------------------------------------------
// Create
// ---------------------------------------------------------------------------

// Create creates a mailbox with the given TTL.
// Use WithPublic to create a publicly discoverable mailbox.
func (c *MQ9Client) Create(ttl int, opts ...CreateOption) (*Mailbox, error) {
	if err := c.ensureConnected(); err != nil {
		return nil, err
	}
	o := &createOptions{}
	for _, opt := range opts {
		opt(o)
	}
	if o.public && o.name == "" {
		return nil, &MQ9Error{Msg: "name is required when public=true"}
	}

	req := map[string]any{"ttl": ttl}
	if o.public {
		req["public"] = true
		req["name"] = o.name
		if o.desc != "" {
			req["desc"] = o.desc
		}
	}

	resp, err := c.request(subjectCreate, req)
	if err != nil {
		return nil, err
	}
	mailID, _ := resp["mail_id"].(string)
	return &Mailbox{MailID: mailID, Public: o.public, Name: o.name, Desc: o.desc}, nil
}

// ---------------------------------------------------------------------------
// Send
// ---------------------------------------------------------------------------

// Send publishes a message to a mailbox. Fire-and-forget.
func (c *MQ9Client) Send(mailID string, payload []byte, priority Priority) error {
	if err := c.ensureConnected(); err != nil {
		return err
	}
	return c.nc.Publish(subjectMsg(mailID, priority), payload)
}

// ---------------------------------------------------------------------------
// Subscribe
// ---------------------------------------------------------------------------

// Subscribe subscribes to messages from a mailbox.
// callback is invoked for each message. Use WithPriority and WithQueueGroup
// to filter or enable competitive consumption.
func (c *MQ9Client) Subscribe(mailID string, callback func(*Message), opts ...SubscribeOption) (*Subscription, error) {
	if err := c.ensureConnected(); err != nil {
		return nil, err
	}
	o := &subscribeOptions{priority: "*"}
	for _, opt := range opts {
		opt(o)
	}
	subject := subjectSub(mailID, o.priority)

	handler := func(raw *nats.Msg) {
		msg := parseIncoming(mailID, raw)
		callback(msg)
	}

	var sub *nats.Subscription
	var err error
	if o.queueGroup != "" {
		sub, err = c.nc.QueueSubscribe(subject, o.queueGroup, handler)
	} else {
		sub, err = c.nc.Subscribe(subject, handler)
	}
	if err != nil {
		return nil, fmt.Errorf("mq9: subscribe: %w", err)
	}
	return &Subscription{sub: sub}, nil
}

// ---------------------------------------------------------------------------
// List
// ---------------------------------------------------------------------------

// List returns a metadata snapshot of all non-expired messages in a mailbox.
// Does not include message payloads — subscribe to receive full messages.
func (c *MQ9Client) List(mailID string) ([]*MessageMeta, error) {
	resp, err := c.request(subjectList(mailID), map[string]any{})
	if err != nil {
		return nil, err
	}
	rawMsgs, _ := resp["messages"].([]any)
	messages := make([]*MessageMeta, 0, len(rawMsgs))
	for _, m := range rawMsgs {
		node, ok := m.(map[string]any)
		if !ok {
			continue
		}
		messages = append(messages, &MessageMeta{
			MsgID:    strVal(node, "msg_id"),
			Priority: toPriority(strVal(node, "priority")),
			Ts:       int64Val(node, "ts"),
		})
	}
	return messages, nil
}

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------

// Delete removes a single message from a mailbox.
func (c *MQ9Client) Delete(mailID, msgID string) error {
	_, err := c.request(subjectDelete(mailID, msgID), map[string]any{})
	return err
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

func (c *MQ9Client) ensureConnected() error {
	if c.nc == nil {
		return &MQ9Error{Msg: "not connected: call Connect() first"}
	}
	return nil
}

func (c *MQ9Client) request(subject string, payload map[string]any) (map[string]any, error) {
	if err := c.ensureConnected(); err != nil {
		return nil, err
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("mq9: marshal: %w", err)
	}
	msg, err := c.nc.Request(subject, data, c.timeout)
	if err != nil {
		return nil, &MQ9Error{Msg: fmt.Sprintf("request failed (%s): %v", subject, err)}
	}
	var resp map[string]any
	if err := json.Unmarshal(msg.Data, &resp); err != nil {
		return nil, fmt.Errorf("mq9: unmarshal response: %w", err)
	}
	if errMsg, ok := resp["error"].(string); ok {
		code := 0
		if c, ok := resp["code"].(float64); ok {
			code = int(c)
		}
		return nil, &MQ9Error{Msg: errMsg, Code: code}
	}
	return resp, nil
}

func parseIncoming(mailID string, raw *nats.Msg) *Message {
	// Subject is either the bare form $mq9.AI.MAILBOX.MSG.{mailID}
	// or the suffixed form $mq9.AI.MAILBOX.MSG.{mailID}.{urgent|critical}
	base := subjectMsgBase(mailID)
	suffix := strings.TrimPrefix(raw.Subject, base)
	priorityStr := strings.TrimPrefix(suffix, ".")
	priority := toPriority(priorityStr) // empty string → Normal

	// Try JSON envelope
	var node map[string]any
	if err := json.Unmarshal(raw.Data, &node); err == nil {
		if _, ok := node["msg_id"]; ok {
			return parseMessageNode(mailID, node)
		}
	}
	return &Message{MailID: mailID, Priority: priority, Payload: raw.Data}
}

func parseMessageNode(mailID string, node map[string]any) *Message {
	rawPayload, _ := node["payload"].(string)
	var payload []byte
	if rawPayload != "" {
		payload, _ = base64.StdEncoding.DecodeString(rawPayload)
	}
	return &Message{
		MsgID:    strVal(node, "msg_id"),
		MailID:   mailID,
		Priority: toPriority(strVal(node, "priority")),
		Payload:  payload,
	}
}

func toPriority(s string) Priority {
	switch s {
	case "critical":
		return Critical
	case "urgent":
		return Urgent
	default:
		return Normal
	}
}

func strVal(m map[string]any, key string) string {
	v, _ := m[key].(string)
	return v
}

func int64Val(m map[string]any, key string) int64 {
	v, _ := m[key].(float64)
	return int64(v)
}
