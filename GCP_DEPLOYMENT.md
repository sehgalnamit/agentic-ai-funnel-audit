# GCP Deployment Guide

This guide walks through deploying the agentic AI funnel audit service to Google Cloud Platform using Terraform.

## Prerequisites

1. **GCP Project**: Create a new GCP project or use an existing one
2. **Terraform**: Install Terraform >= 1.0
3. **gcloud CLI**: Install and authenticate with your GCP account
4. **Docker**: For building and pushing container images
5. **OpenAI API Key** (optional): If you want model-driven scoring

## Quick Start

### 1. Prepare the Container Image

```bash
# From the repository root
docker build -t agentic-ai-funnel-audit:latest .

# Set your GCP project
export GCP_PROJECT_ID=your-gcp-project-id
export GCP_REGION=us-central1

# Tag the image for Artifact Registry
docker tag agentic-ai-funnel-audit:latest \
  ${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/agentic-ai-funnel-audit/agentic-ai-funnel-audit:latest
```

### 2. Configure Authentication

```bash
# Login to gcloud
gcloud auth login

# Set default project
gcloud config set project $GCP_PROJECT_ID

# Configure Docker authentication for Artifact Registry
gcloud auth configure-docker ${GCP_REGION}-docker.pkg.dev
```

### 3. Push the Image to Artifact Registry

```bash
docker push ${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/agentic-ai-funnel-audit/agentic-ai-funnel-audit:latest
```

### 4. Deploy with Terraform

```bash
cd terraform

# Copy and edit the example configuration
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your values
# - project_id: Your GCP project ID
# - region: Your preferred GCP region
# - enable_model_scoring: Set to true if you have OPENAI_API_KEY configured

# Initialize Terraform
terraform init

# Plan the deployment
terraform plan

# Apply the configuration
terraform apply
```

### 5. Set Secret Manager Values

After deployment, set your secrets:

```bash
# Set OpenAI API key (if using model-driven scoring)
echo -n "your-openai-api-key" | gcloud secrets versions add openai-api-key --data-file=-

# Set telemetry source configuration (e.g., Datadog, Prometheus endpoint)
echo -n "datadog" | gcloud secrets versions add telemetry-source-config --data-file=-
```

### 6. Access the Service

The Terraform output will provide the Cloud Run URL:

```bash
# Get the Cloud Run URL
terraform output cloud_run_url

# Example: https://agentic-ai-funnel-audit-xxxxx-uc.a.run.app

# Test the health endpoint
curl https://agentic-ai-funnel-audit-xxxxx-uc.a.run.app/
```

## Testing the Deployment

### Submit an Audit

```bash
curl -X POST https://agentic-ai-funnel-audit-xxxxx-uc.a.run.app/audit \
  -H "Content-Type: application/json" \
  -d '{
    "idea": {
      "id": "idea-001",
      "description": "Build a real-time analytics hub",
      "dependencies": ["data-platform"],
      "trend_score": 4,
      "strategic_fit": 4
    },
    "context": {
      "data_maturity": 4,
      "competitor_signal": 3
    }
  }'
```

### Get Enriched Context from Operational Data

```bash
curl "https://agentic-ai-funnel-audit-xxxxx-uc.a.run.app/audit/idea-001/enrich?service_id=analytics-service&team_id=platform-team"
```

### Record an Outcome

```bash
curl -X POST https://agentic-ai-funnel-audit-xxxxx-uc.a.run.app/outcomes \
  -H "Content-Type: application/json" \
  -d '{
    "idea_id": "idea-001",
    "outcome_status": "success",
    "implementation_duration_weeks": 8,
    "actual_delivery_cost": 250000,
    "actual_team_velocity_impact": 2,
    "business_value_realized": 5,
    "risk_incidents_count": 0,
    "technical_debt_added": 1,
    "process_improvements": ["automated-testing"],
    "lessons_learned": "Model performed well on this use case"
  }'
```

### Get Calibration Factors

```bash
curl https://agentic-ai-funnel-audit-xxxxx-uc.a.run.app/calibration
```

## Configuring Data Sources

The service supports pluggable connectors for operational data. By default, it uses mock data. To integrate real sources:

### Datadog Integration

Set environment variable:
```bash
export TELEMETRY_SOURCE=datadog
export DATADOG_API_KEY=your-api-key
export DATADOG_APP_KEY=your-app-key
```

Then update `src/agentic_ai_funnel_audit/connectors.py` to implement the Datadog client.

### Prometheus Integration

Set environment variable:
```bash
export TELEMETRY_SOURCE=prometheus
export PROMETHEUS_URL=https://prometheus.example.com
```

### Jira Integration

Set environment variable:
```bash
export BACKLOG_SOURCE=jira
export JIRA_URL=https://jira.example.com
export JIRA_API_TOKEN=your-token
```

## Event-Driven Ingestion with Pub/Sub

The deployment includes a Pub/Sub topic for event-driven idea submission. To publish ideas:

```bash
# Publish an idea to the topic
gcloud pubsub topics publish agentic-ai-funnel-audit-ideas \
  --message '{
    "idea": {
      "id": "idea-from-event",
      "description": "Event-driven idea",
      "dependencies": [],
      "trend_score": 4,
      "strategic_fit": 4
    },
    "context": {
      "data_maturity": 3
    }
  }'
```

Cloud Run will automatically receive and process the event through its Pub/Sub subscription.

## Monitoring and Logs

View Cloud Run logs:

```bash
gcloud run services describe agentic-ai-funnel-audit --region $GCP_REGION
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=agentic-ai-funnel-audit" --limit 50
```

## Cost Optimization

- **Cloud Run**: Pay per request; use auto-scaling
- **Artifact Registry**: Store only the latest image to save storage costs
- **Storage**: Use lifecycle policies to transition logs to cheaper tiers (e.g., NEARLINE after 90 days)
- **Secret Manager**: Minimal cost (~$0.06/secret/month)

## Cleanup

To tear down all resources:

```bash
cd terraform
terraform destroy
```

## Troubleshooting

### Image not found in Artifact Registry

Ensure you've pushed the image:
```bash
docker push ${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/agentic-ai-funnel-audit/agentic-ai-funnel-audit:latest
```

### Cloud Run service fails to start

Check logs:
```bash
gcloud run services describe agentic-ai-funnel-audit --region $GCP_REGION
gcloud logging read --limit 50
```

### Permission errors

Ensure your service account has required IAM roles:
- `roles/secretmanager.secretAccessor`
- `roles/storage.objectAdmin`
- `roles/pubsub.subscriber`

## Next Steps

1. Integrate real operational data sources (Datadog, Prometheus, Jira)
2. Configure custom approval workflows and policy hooks
3. Set up monitoring dashboards in Cloud Monitoring
4. Implement email notifications for audit results
5. Create a frontend dashboard for reviewers
