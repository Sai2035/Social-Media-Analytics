Social Media Analytics Platform
A web-based social media analytics platform designed for creators and brands to gain actionable insights from Instagram data.
The application integrates third-party Instagram APIs to collect engagement metrics, track follower growth, analyze post performance, and visualize insights for data-driven decision making.

Overview
This platform provides role-based analytics through two dedicated modules:

Brand Dashboard – Compare influencers within a niche and evaluate campaign potential.
Creator Dashboard – Analyze individual account performance using username-based insights.
The system processes engagement data, computes key performance metrics, performs sentiment analysis, and visualizes results using interactive charts and graphs.

Key Features
Brand Module
Niche-based comparison of up to 10 influencers
Engagement rate calculation (based on last 3 posts)
Follower growth tracking
Comment sentiment analysis
Detailed influencer profile insights
CSV export for offline reporting
Creator Module
Username-based performance analysis
Engagement rate calculation
Follower growth monitoring
Comment sentiment breakdown
Data visualization through charts
Metrics & Visualization
Engagement Rate
Calculated using likes and comments from the last three posts relative to the current follower count.

Follower Growth
Measures change in follower count over time.

Growth Visualization Logic
Follower growth and engagement rate growth are displayed using line graphs.

Instead of showing only absolute values, the system compares:

The current fetched dataset
The dataset stored during the previous fetch
When a user fetches data again, the backend calculates growth as:

Current Value − Previously Cached Value

The previous dataset is stored in SQLite3 using a 12-hour caching mechanism.
This enables meaningful performance comparison while efficiently managing third-party API rate limits.

Tech Stack
Frontend
HTML
CSS
JavaScript
Backend
Python
Flask (REST API architecture)
Database
SQLite3
Used for storing analytics data and implementing a 12-hour caching mechanism.
System Architecture
User selects either the Brand or Creator module.
The Flask backend fetches Instagram data using third-party APIs.
Data is processed to compute engagement metrics, growth differences, and sentiment analysis.
Responses are cached in SQLite3 for 12 hours.
The frontend retrieves processed data via REST endpoints.
JavaScript dynamically renders line graphs, bar charts, and pie charts.
Users can export results as CSV for reporting purposes.
Technical Design Decisions
Implemented a 12-hour caching mechanism to minimize redundant API calls and manage rate limitations.
Designed modular Flask API endpoints to ensure separation of concerns.
Stored previous fetch snapshots to enable delta-based growth comparison.
Integrated CSV export functionality for offline analytics and reporting.
Objective
To bridge the gap between raw social media metrics and actionable insights by providing structured, role-based analytics for both creators and brands.

Configuration
This project integrates a third-party Instagram data API.

Create a .env file in the root directory.
Add your API credentials in the following format:
API_KEY=your_api_key_here

Ensure the application loads environment variables before starting the Flask server.
Note: The .env file is excluded from version control for security reasons.

Future Improvements
Real-time analytics updates
Advanced sentiment modeling
Influencer ranking algorithm
Campaign ROI prediction metrics
Cloud deployment
Author
Sai Nandhana
