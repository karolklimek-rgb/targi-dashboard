#!/bin/bash
cd "$(dirname "$0")"
open "http://localhost:8511"
streamlit run app.py --server.port 8511 --server.headless true
