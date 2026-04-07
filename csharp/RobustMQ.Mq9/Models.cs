namespace RobustMQ.Mq9;

public enum Priority
{
    High,
    Normal,
    Low
}

internal static class PriorityExtensions
{
    public static string ToSubjectString(this Priority p) => p switch
    {
        Priority.High => "high",
        Priority.Normal => "normal",
        Priority.Low => "low",
        _ => "normal"
    };

    public static Priority FromString(string s) => s switch
    {
        "high" => Priority.High,
        "low" => Priority.Low,
        _ => Priority.Normal
    };
}

public record Mailbox(string MailId, bool Public, string Name, string Desc);

public record MessageMeta(string MsgId, Priority Priority, long Ts);

public record Mq9Message(
    string MsgId,
    string MailId,
    Priority Priority,
    byte[] Payload);

public class MQ9Error : Exception
{
    public int Code { get; }

    public MQ9Error(string message, int code = 0) : base(message)
    {
        Code = code;
    }
}
