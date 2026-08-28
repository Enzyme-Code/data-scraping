# Data Scraping

<details open>
<summary><b>English</b></summary>

A modular data ingestion hub designed to collect and process various open data sources, including weather and air quality data.

### Project Overview

This project serves as the centralized data fetching engine for the back-end system. It utilizes a provider-pipeline architecture to ensure scalability and maintainability across different data domains.

### Directory Structure

- `weather/`: CWA (Central Weather Administration) data ingestion.
- `air/`: Ministry of Environment air quality data ingestion.
- `storage/`: Database connection and data persistence logic.
- `utils/`: Common utilities (e.g., HTTP client with retry logic, logging).

### Getting Started

#### Prerequisites
- **Python Version**: 3.12.10 (Recommended)

#### 1. Environment Setup
Create a virtual environment to isolate project dependencies:
```bash
python -m venv .venv
```
#### 2. Environment entering

**Windows**
```bash
.venv\Scripts\activate
```

**macOS / Linux**
```bash
source .venv/bin/activate
```

</details>

<details>
<summary><b>繁體中文</b></summary>

一個模組化的資料擷取中心，用於收集並處理各種公開資料來源，包含天氣與空氣品質資料。

### 專案概覽

本專案作為後端系統的集中式資料擷取引擎，採用 provider-pipeline 架構，確保在不同資料領域間具備可擴充性與可維護性。

### 目錄結構

- `weather/`：中央氣象署（CWA）資料擷取。
- `air/`：環境部空氣品質資料擷取。
- `storage/`：資料庫連線與資料持久化邏輯。
- `utils/`：共用工具（例如具重試機制的 HTTP client、日誌記錄）。

### 快速開始

#### 事前準備
- **Python 版本**：3.12.10（建議版本）

#### 1. 建立虛擬環境
建立虛擬環境以隔離專案相依套件：
```bash
python -m venv .venv
```
#### 2. 進入虛擬環境

**Windows**
```bash
.venv\Scripts\activate
```

**macOS / Linux**
```bash
source .venv/bin/activate
```

</details>
