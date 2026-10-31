{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteState",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:${partition}:s3:::${state_bucket}/${state_key}"
    },
    {
      "Sid": "ChangeWorkloadRolesOnlyWithBoundary",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole", "iam:PutRolePermissionsBoundary", "iam:PutRolePolicy",
        "iam:DeleteRolePolicy", "iam:AttachRolePolicy", "iam:DetachRolePolicy"
      ],
      "Resource": "arn:${partition}:iam::${account_id}:role/${project}-*",
      "Condition": { "StringEquals": { "iam:PermissionsBoundary": "${boundary_arn}" } }
    },
    {
      "Sid": "ManageWorkloadRoles",
      "Effect": "Allow",
      "Action": ["iam:DeleteRole", "iam:UpdateRole", "iam:UpdateAssumeRolePolicy", "iam:TagRole", "iam:UntagRole"],
      "Resource": "arn:${partition}:iam::${account_id}:role/${project}-*"
    },
    {
      "Sid": "PassOnlyLambdaRolesToLambda",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:${partition}:iam::${account_id}:role/${project}-api",
        "arn:${partition}:iam::${account_id}:role/${project}-worker"
      ],
      "Condition": { "StringEquals": { "iam:PassedToService": "lambda.amazonaws.com" } }
    },
    {
      "Sid": "LambdaFunctions",
      "Effect": "Allow",
      "Action": [
        "lambda:CreateFunction", "lambda:DeleteFunction", "lambda:UpdateFunctionCode",
        "lambda:UpdateFunctionConfiguration", "lambda:AddPermission", "lambda:RemovePermission",
        "lambda:TagResource", "lambda:UntagResource"
      ],
      "Resource": "arn:${partition}:lambda:${region}:${account_id}:function:${project}-*"
    },
    {
      "Sid": "EventSourceMappingsForOwnFunctions",
      "Effect": "Allow",
      "Action": ["lambda:CreateEventSourceMapping", "lambda:UpdateEventSourceMapping", "lambda:DeleteEventSourceMapping"],
      "Resource": "*",
      "Condition": { "StringLike": { "lambda:FunctionArn": "arn:${partition}:lambda:${region}:${account_id}:function:${project}-*" } }
    },
    {
      "Sid": "FleetTable",
      "Effect": "Allow",
      "Action": [
        "dynamodb:CreateTable", "dynamodb:DeleteTable", "dynamodb:UpdateTable", "dynamodb:UpdateTimeToLive",
        "dynamodb:UpdateContinuousBackups", "dynamodb:TagResource", "dynamodb:UntagResource"
      ],
      "Resource": "arn:${partition}:dynamodb:${region}:${account_id}:table/${project}-*"
    },
    {
      "Sid": "Queues",
      "Effect": "Allow",
      "Action": ["sqs:CreateQueue", "sqs:DeleteQueue", "sqs:SetQueueAttributes", "sqs:TagQueue", "sqs:UntagQueue"],
      "Resource": "arn:${partition}:sqs:${region}:${account_id}:${project}-*"
    },
    {
      "Sid": "LogGroups",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy", "logs:DeleteRetentionPolicy",
        "logs:TagResource", "logs:UntagResource", "logs:TagLogGroup", "logs:UntagLogGroup"
      ],
      "Resource": [
        "arn:${partition}:logs:${region}:${account_id}:log-group:/aws/lambda/${project}-*",
        "arn:${partition}:logs:${region}:${account_id}:log-group:/aws/apigateway/${project}*"
      ]
    },
    {
      "Sid": "HttpApiAccessLogDelivery",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery", "logs:DeleteLogDelivery",
        "logs:ListLogDeliveries", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies"
      ],
      "Resource": "*"
    },
    {
      "Sid": "HttpApi",
      "Effect": "Allow",
      "Action": ["apigateway:POST", "apigateway:PUT", "apigateway:PATCH", "apigateway:DELETE"],
      "Resource": [
        "arn:${partition}:apigateway:${region}::/apis",
        "arn:${partition}:apigateway:${region}::/apis/*",
        "arn:${partition}:apigateway:${region}::/tags/*"
      ]
    },
    {
      "Sid": "OperatorUserPoolCreate",
      "Effect": "Allow",
      "Action": "cognito-idp:CreateUserPool",
      "Resource": "*",
      "Condition": { "StringEquals": { "aws:RequestedRegion": "${region}" } }
    },
    {
      "Sid": "OperatorUserPool",
      "Effect": "Allow",
      "Action": [
        "cognito-idp:UpdateUserPool", "cognito-idp:DeleteUserPool", "cognito-idp:CreateUserPoolClient",
        "cognito-idp:UpdateUserPoolClient", "cognito-idp:DeleteUserPoolClient", "cognito-idp:SetUserPoolMfaConfig",
        "cognito-idp:TagResource", "cognito-idp:UntagResource"
      ],
      "Resource": "arn:${partition}:cognito-idp:${region}:${account_id}:userpool/*"
    },
    {
      "Sid": "FrontendDistribution",
      "Effect": "Allow",
      "Action": [
        "cloudfront:CreateDistribution", "cloudfront:UpdateDistribution", "cloudfront:DeleteDistribution",
        "cloudfront:CreateInvalidation", "cloudfront:TagResource", "cloudfront:UntagResource",
        "cloudfront:CreateOriginAccessControl", "cloudfront:UpdateOriginAccessControl", "cloudfront:DeleteOriginAccessControl",
        "cloudfront:CreateResponseHeadersPolicy", "cloudfront:UpdateResponseHeadersPolicy", "cloudfront:DeleteResponseHeadersPolicy"
      ],
      "Resource": "arn:${partition}:cloudfront::${account_id}:*"
    },
    {
      "Sid": "FrontendBucket",
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket", "s3:DeleteBucket", "s3:PutBucket*", "s3:DeleteBucketPolicy", "s3:PutEncryptionConfiguration",
        "s3:PutObject", "s3:PutObjectTagging", "s3:DeleteObject", "s3:DeleteObjectVersion"
      ],
      "Resource": ["arn:${partition}:s3:::${project}-*", "arn:${partition}:s3:::${project}-*/*"]
    },
    {
      "Sid": "AlertsAndAlarms",
      "Effect": "Allow",
      "Action": [
        "sns:CreateTopic", "sns:DeleteTopic", "sns:SetTopicAttributes", "sns:Subscribe", "sns:Unsubscribe",
        "sns:TagResource", "sns:UntagResource",
        "cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms", "cloudwatch:TagResource", "cloudwatch:UntagResource"
      ],
      "Resource": [
        "arn:${partition}:sns:${region}:${account_id}:${project}-*",
        "arn:${partition}:cloudwatch:${region}:${account_id}:alarm:${project}-*"
      ]
    },
    {
      "Sid": "NeverWeakenTheBoundaryOrCreateCredentials",
      "Effect": "Deny",
      "Action": [
        "iam:DeleteRolePermissionsBoundary", "iam:CreatePolicyVersion", "iam:DeletePolicy", "iam:DeletePolicyVersion",
        "iam:SetDefaultPolicyVersion", "iam:CreateUser", "iam:CreateAccessKey", "iam:CreateLoginProfile"
      ],
      "Resource": "*"
    },
    {
      "Sid": "NeverTouchDeployRoles",
      "Effect": "Deny",
      "Action": "iam:*",
      "Resource": "arn:${partition}:iam::${account_id}:role/${deploy_role_prefix}*"
    },
    {
      "Sid": "NeverManageOperators",
      "Effect": "Deny",
      "Action": ["cognito-idp:Admin*", "cognito-idp:SignUp"],
      "Resource": "*"
    },
    {
      "Sid": "NeverWeakenStateBucket",
      "Effect": "Deny",
      "Action": [
        "s3:DeleteBucket", "s3:PutBucketPolicy", "s3:DeleteBucketPolicy", "s3:PutBucketVersioning",
        "s3:PutLifecycleConfiguration", "s3:PutEncryptionConfiguration", "s3:PutBucketPublicAccessBlock"
      ],
      "Resource": "arn:${partition}:s3:::${state_bucket}"
    }
  ]
}
