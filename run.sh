#!/bin/bash

# 인자: 로그 디렉토리 이름, 부하 시간(초), 전체 실험 시간(초)
LOG_DIR=$1
STRESS_TIME=$2
TOTAL_DURATION=$3

# 필수 인자 확인
if [ -z "$LOG_DIR" ] || [ -z "$STRESS_TIME" ] || [ -z "$TOTAL_DURATION" ]; then
  echo "❌ 사용법: ./run_test.sh <log_dir> <stress_time> <total_duration>"
  exit 1
fi

echo "🔧 IPMI 권한 테스트 중..."
sudo ipmitool dcmi power reading

echo "🚀 Python 스크립트 실행 중..."
python run_and_analyze_v3.py \
  --log_dir "$LOG_DIR" \
  --stress_time "$STRESS_TIME" \
  --total_duration "$TOTAL_DURATION"
