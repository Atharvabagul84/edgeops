{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RefreshStackResources",
      "Effect": "Allow",
      "Action": [
        "apigateway:GET",
        "cloudfront:Get*", "cloudfront:List*",
        "cloudwatch:DescribeAlarms", "cloudwatch:ListTagsForResource",
        "cognito-idp:DescribeUserPool", "cognito-idp:DescribeUserPoolClient",
        "cognito-idp:GetUserPoolMfaConfig", "cognito-idp:ListTagsForResource",
        "dynamodb:DescribeTable", "dynamodb:DescribeContinuousBackups",
        "dynamodb:DescribeTimeToLive", "dynamodb:ListTagsOfResource",
        "iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies",
        "lambda:GetFunction", "lambda:GetFunctionCodeSigningConfig", "lambda:GetPolicy",
        "lambda:GetEventSourceMapping", "lambda:ListVersionsByFunction", "lambda:ListTags",
        "logs:DescribeLogGroups", "logs:ListTagsForResource", "logs:ListTagsLogGroup",
        "sns:GetTopicAttributes", "sns:GetSubscriptionAttributes", "sns:ListTagsForResource",
        "sns:ListSubscriptionsByTopic",
        "sqs:GetQueueAttributes", "sqs:GetQueueUrl", "sqs:ListQueueTags"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ReadFrontendBucket",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket", "s3:GetBucket*", "s3:GetAccelerateConfiguration", "s3:GetEncryptionConfiguration",
        "s3:GetLifecycleConfiguration", "s3:GetReplicationConfiguration", "s3:GetObject", "s3:GetObjectTagging"
      ],
      "Resource": ["arn:${partition}:s3:::${project}-*", "arn:${partition}:s3:::${project}-*/*"]
    },
    {
      "Sid": "ListStateBucket",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:${partition}:s3:::${state_bucket}"
    },
    {
      "Sid": "ReadState",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:${partition}:s3:::${state_bucket}/${state_key}"
    },
    {
      "Sid": "StateLockFile",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:${partition}:s3:::${state_bucket}/${state_key}.tflock"
    }
  ]
}
