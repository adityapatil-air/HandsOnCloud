#!/bin/bash
# No-op: EC2 CodeDeploy lifecycle hook removed.
# Deployment is now handled by CodeBuild (buildspec.yml) directly updating Lambda.
echo "before_install: nothing to do (serverless deployment)"
