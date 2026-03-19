# Data Scraping

A modular data ingestion hub designed to collect and process various open data sources, including weather, air quality, and stock market data.

## Project Overview

This project serves as the centralized data fetching engine for the back-end system. It utilizes a provider-pipeline architecture to ensure scalability and maintainability across different data domains.

## Directory Structure

- `weather/`: CWA (Central Weather Administration) data ingestion.
- `air/`: Ministry of Environment air quality data ingestion.
- `stock/`: Market price and macroeconomic data scraping.
- `storage/`: Database connection and data persistence logic.
- `utils/`: Common utilities (e.g., HTTP client with retry logic, logging).

## Getting Started

### Prerequisites
- **Python Version**: 3.14.3 (Recommended)

### 1. Environment Setup
Create a virtual environment to isolate project dependencies:
```bash
python -m venv .venv
```
### 2. Environment entering
```bash
.venv\Scripts\activate
```
