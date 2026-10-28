resource "aws_sns_topic" "alerts" {
  count = var.alarm_email == "" ? 0 : 1
  name  = "${local.name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "dead_letters" {
  alarm_name          = "${local.name}-dead-letters"
  alarm_description   = "Telemetry could not be processed after five attempts. Inspect and fix before redrive."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = aws_sqs_queue.dead_letter.name }
  alarm_actions       = aws_sns_topic.alerts[*].arn
}

resource "aws_cloudwatch_metric_alarm" "write_throttles" {
  alarm_name          = "${local.name}-state-write-throttles"
  alarm_description   = "Single-item demo throughput exceeded; slow the simulator, then retry."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "WriteThrottleEvents"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions          = { TableName = aws_dynamodb_table.state.name }
  alarm_actions       = aws_sns_topic.alerts[*].arn
}
