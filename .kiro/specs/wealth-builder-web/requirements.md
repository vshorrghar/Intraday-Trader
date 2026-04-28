# Requirements Document

## Introduction

Wealth Builder Web is a public-facing web application that exposes the existing Wealth Builder Pro portfolio analysis engine to anyone on the internet. Users upload their Groww broker XLSX exports (Stocks Holdings, Mutual Funds, Order History), and the system runs the full analysis pipeline (parsing, market data fetching, Claude LLM analysis) on the existing EC2 instance in Mumbai, returning an interactive 6-tab dashboard experience identical to the private tool. A pre-loaded demo portfolio ("Ramesh Kumar") lets visitors explore the dashboard without uploading files. The existing private `./go.sh` workflow must remain fully operational and unaffected.

## Glossary

- **Frontend**: A static single-page application hosted on Netlify that provides the file upload UI and dashboard rendering
- **API_Server**: A Python HTTP server (FastAPI) running on the existing EC2 instance in Mumbai (ap-south-1) that receives XLSX uploads, runs the analysis pipeline, and returns JSON results
- **Analysis_Pipeline**: The sequence of parsing Groww XLSX files, fetching live market data, invoking Claude via Bedrock, and building the dashboard JSON — reusing existing parsers, fetchers, and LLM modules
- **Demo_Mode**: A feature that serves a pre-generated analysis JSON for a fictional "Ramesh Kumar" portfolio so visitors can explore the dashboard without uploading files
- **Upload_Session**: A temporary server-side context created when a user uploads XLSX files, identified by a unique session ID, with a defined time-to-live
- **Private_Tool**: The existing `./go.sh` CLI workflow that syncs code to EC2, runs analysis, pulls results to the user's Mac, and opens a local dashboard — this must not be broken
- **Dashboard**: The 6-tab interactive UI (Portfolio, MFs & SIPs, My Decisions, Buy Now, Intraday, Market Intel) that renders analysis results

## Requirements

### Requirement 1: XLSX File Upload

**User Story:** As a public user, I want to upload my Groww XLSX export files through a web interface, so that I can get my portfolio analyzed without needing CLI tools or EC2 access.

#### Acceptance Criteria

1. THE Frontend SHALL provide a file upload form that accepts up to three XLSX files: Stocks Holdings Statement, Mutual Funds, and Stocks Order History
2. WHEN a user selects files for upload, THE Frontend SHALL validate that each file has an `.xlsx` extension before sending to the API_Server
3. WHEN a user submits the upload form, THE Frontend SHALL send all selected XLSX files to the API_Server in a single multipart HTTP POST request
4. THE API_Server SHALL accept multipart file uploads at a dedicated `/api/upload` endpoint
5. WHEN the API_Server receives an upload, THE API_Server SHALL create an Upload_Session with a unique session ID and return the session ID to the Frontend within 2 seconds
6. IF a file exceeds 10 MB in size, THEN THE API_Server SHALL reject the upload and return an error message stating the size limit
7. IF no Stocks Holdings Statement file is included in the upload, THEN THE API_Server SHALL reject the upload and return an error message indicating that the Stocks Holdings file is required
8. THE API_Server SHALL delete uploaded XLSX files and all derived data for an Upload_Session after 30 minutes

### Requirement 2: Portfolio Analysis Pipeline Execution

**User Story:** As a public user, I want the system to analyze my uploaded portfolio using the same engine as the private tool, so that I get the same quality of AI-powered insights.

#### Acceptance Criteria

1. WHEN an Upload_Session is created with valid XLSX files, THE API_Server SHALL execute the Analysis_Pipeline using the existing parsers (`groww_stocks_parser`, `groww_mf_parser`) on the uploaded files
2. WHEN the Stocks Holdings file is parsed, THE API_Server SHALL invoke the existing Bedrock Claude model (`us.anthropic.claude-sonnet-4-20250514-v1:0`) via the existing `BedrockClient` to generate portfolio verdicts
3. WHEN the analysis is running, THE API_Server SHALL execute the market scan pipeline using the existing fetchers (FII/DII, bulk deals, AMFI NAV) and the `market_scanner` LLM module
4. WHEN the Analysis_Pipeline completes, THE API_Server SHALL build the dashboard JSON using the same merging logic as `build_dashboard.py`
5. WHEN the Analysis_Pipeline completes, THE API_Server SHALL store the resulting dashboard JSON associated with the Upload_Session
6. IF a parser raises a `ValueError` due to unexpected XLSX format, THEN THE API_Server SHALL return a descriptive error message to the Frontend indicating which file failed validation
7. IF the Bedrock invocation fails or returns an empty response, THEN THE API_Server SHALL return a partial result with parsed portfolio data and a warning that AI analysis is unavailable

### Requirement 3: Analysis Status Polling

**User Story:** As a public user, I want to see the progress of my portfolio analysis, so that I know the system is working and can estimate wait time.

#### Acceptance Criteria

1. THE API_Server SHALL expose a `/api/status/{session_id}` endpoint that returns the current state of an Upload_Session
2. WHEN the Analysis_Pipeline is running, THE API_Server SHALL report status as one of: `uploading`, `parsing`, `fetching_market_data`, `analyzing`, `building_dashboard`, `complete`, or `error`
3. WHEN the Frontend receives a session ID, THE Frontend SHALL poll the status endpoint every 3 seconds until the status is `complete` or `error`
4. WHEN the status is `complete`, THE Frontend SHALL fetch the dashboard JSON from the API_Server and render the dashboard
5. IF the status is `error`, THEN THE Frontend SHALL display the error message returned by the API_Server

### Requirement 4: Dashboard Rendering

**User Story:** As a public user, I want to see the same 6-tab dashboard experience as the private tool, so that I get a comprehensive view of my portfolio analysis.

#### Acceptance Criteria

1. THE Frontend SHALL render a 6-tab dashboard with tabs: Portfolio, MFs & SIPs, My Decisions, Buy Now, Intraday, and Market Intel
2. WHEN dashboard JSON is loaded, THE Frontend SHALL populate the Portfolio tab with stock verdicts, portfolio health score, summary metrics, and urgent actions
3. WHEN dashboard JSON is loaded, THE Frontend SHALL populate the MFs & SIPs tab with mutual fund verdicts, SIP status, and goal tracker
4. WHEN dashboard JSON is loaded, THE Frontend SHALL populate the My Decisions tab with recent stock buy grades and SIP analysis
5. WHEN dashboard JSON is loaded, THE Frontend SHALL populate the Buy Now tab wit