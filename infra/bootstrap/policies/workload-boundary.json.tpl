{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "OwnLogStreams",
      "Effect": "Allow",
      "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:${partition}:logs:${region}:${account_id}:log-group:/aws/lambda/${project}-*"
    },
    {
      "Sid": "FleetTableItems",
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:PutItem"],
      "Resource": "arn:${partition}:dynamodb:${region}:${account_id}:table/${project}-*"
    },
    {
      "Sid": "TelemetryQueues",
      "Effect": "Allow",
      "Action": ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
      "Resource": "arn:${partition}:sqs:${region}:${account_id}:${project}-*"
    }
  ]
}
