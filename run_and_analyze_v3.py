import os
import time
import threading
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import csv
import argparse

# ---------------------- 인자 파싱 ----------------------
parser = argparse.ArgumentParser()
parser.add_argument("--log_dir", type=str, required=True, help="로그 저장 디렉토리")
parser.add_argument("--stress_time", type=int, default=3600, help="GPU Burn 및 stress-ng 부하 시간 (초)")
parser.add_argument("--total_duration", type=int, default=3600, help="전체 실험 시간 (초)")
args = parser.parse_args()

# ---------------------- 디렉토리 설정 ----------------------
log_dir = args.log_dir
os.makedirs(log_dir, exist_ok=True)

gpu_log_path_0 = os.path.join(log_dir, "gpu_log_0.csv")
gpu_log_path_1 = os.path.join(log_dir, "gpu_log_1.csv")
ipmi_log_path = os.path.join(log_dir, "ipmi_power_log.csv")
temp_log_path = os.path.join(log_dir, "temp_log.txt")
stress_log_path = os.path.join(log_dir, "stress_log.txt")
graph_output_path_0 = os.path.join(log_dir, "gpu0_graph.png")
graph_output_path_1 = os.path.join(log_dir, "gpu1_graph.png")
ipmi_graph_path = os.path.join(log_dir, "ipmi_power_graph.png")

# -------------------------- 로그 수집 함수 --------------------------
def log_gpu(index, path):
    with open(path, "w") as f:
        f.write("timestamp, utilization.gpu [%], power.draw [W], temperature.gpu [C]\n")
        while not stop_logging.is_set():
            result = subprocess.run([
                "nvidia-smi", f"--id={index}",
                "--query-gpu=timestamp,utilization.gpu,power.draw,temperature.gpu",
                "--format=csv,noheader,nounits"
            ], capture_output=True, text=True)
            f.write(result.stdout)
            f.flush()
            time.sleep(1)

def log_temp():
    with open(temp_log_path, "w") as f:
        while not stop_logging.is_set():
            subprocess.run(["sensors"], stdout=f)
            f.write("---\n")
            f.flush()
            time.sleep(1)

def log_ipmi_power():
    with open(ipmi_log_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Timestamp", "Instantaneous(W)", "Min(W)", "Max(W)", "Avg(W)", "SamplingPeriod(s)"])
        csvfile.flush()
        while not stop_logging.is_set():
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            try:
                output = subprocess.check_output(["ipmitool", "dcmi", "power", "reading"]).decode()
                lines = output.splitlines()
                data = { "Instantaneous": "", "Minimum": "", "Maximum": "", "Average": "", "Sampling": "" }
                for line in lines:
                    if "Instantaneous power reading" in line:
                        data["Instantaneous"] = line.split(":")[1].strip().split()[0]
                    elif "Minimum during sampling period" in line:
                        data["Minimum"] = line.split(":")[1].strip().split()[0]
                    elif "Maximum during sampling period" in line:
                        data["Maximum"] = line.split(":")[1].strip().split()[0]
                    elif "Average power reading" in line:
                        data["Average"] = line.split(":")[1].strip().split()[0]
                    elif "Sampling period" in line:
                        data["Sampling"] = line.split()[3]
                writer.writerow([timestamp, data["Instantaneous"], data["Minimum"], data["Maximum"], data["Average"], data["Sampling"]])
                csvfile.flush() 
            except Exception as e:
                writer.writerow([timestamp, "ERROR", "", "", "", str(e)])
            time.sleep(1)

# 전역 또는 main 함수 시작 부분에
fig_gpu0, axs_gpu0 = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
fig_gpu1, axs_gpu1 = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
fig_ipmi, ax_ipmi = plt.subplots(figsize=(10, 3))

# -------------------------- 시각화 함수 --------------------------
def plot_gpu_log(path, fig, axs, output_path, title):
    df = pd.read_csv(path)
    df.columns = [col.strip() for col in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["power"] = df["power.draw [W]"].astype(float)
    df["temp"] = df["temperature.gpu [C]"].astype(float)

    axs[0].cla(); axs[1].cla()

    axs[0].plot(df["timestamp"], df["power"], label="Power Draw (W)", color="tab:blue")
    axs[1].plot(df["timestamp"], df["temp"], label="GPU Temp (°C)", color="tab:red")

    axs[0].set_ylabel("Power (W)")
    axs[1].set_ylabel("Temp (°C)")
    axs[1].set_xlabel("Time")

    axs[0].legend(loc='upper left', bbox_to_anchor=(1.0, 1.0), fontsize='small')
    axs[1].legend(loc='upper left', bbox_to_anchor=(1.0, 1.0), fontsize='small')
    axs[0].grid(); axs[1].grid()

    fig.suptitle(title)
    fig.tight_layout()
    fig.subplots_adjust(right=0.82, top=0.90)
    fig.savefig(output_path)


def plot_ipmi_log(path, fig, ax, output_path):
    df = pd.read_csv(path)
    df.columns = [col.strip() for col in df.columns]
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    df["Avg(W)"] = pd.to_numeric(df["Avg(W)"], errors='coerce')

    ax.cla()
    ax.plot(df["Timestamp"], df["Avg(W)"], label="Average")
    ax.set_title("System Power (IPMI)")
    ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), fontsize='small')
    ax.grid()

    fig.tight_layout()
    fig.subplots_adjust(top=0.85)
    fig.savefig(output_path)


# -------------------------- GPU Burn 및 Stress-ng --------------------------
def run_gpu_burn(index):
    subprocess.run([
        "bash", "-c", f"CUDA_VISIBLE_DEVICES={index} /home/kyumin/gpu-test/gpu-burn/gpu_burn {args.stress_time}"
    ], cwd="/home/kyumin/gpu-test/gpu-burn")

def run_stress_ng():
    with open(stress_log_path, "w") as f:
        subprocess.run([
            "stress-ng", "--cpu", "16",
            "--vm", "4", "--vm-bytes", "500M",
            "--hdd", "4", "--hdd-bytes", "500M",
            "--timeout", f"{args.stress_time}s", "--metrics-brief"
        ], stdout=f, stderr=f)

# -------------------------- 주기적 시각화 스레드 --------------------------
def periodic_visualization(interval_sec=30, duration_sec=args.total_duration):
    num_iterations = duration_sec // interval_sec + 1
    for i in range(num_iterations):
        start = time.time()

        print(f"📊 시각화 실행 (회차 {i})")
        try:
            plot_gpu_log(gpu_log_path_0, fig_gpu0, axs_gpu0, graph_output_path_0, "GPU 0 Power & Temp")
            plot_gpu_log(gpu_log_path_1, fig_gpu1, axs_gpu1, graph_output_path_1, "GPU 1 Power & Temp")
            plot_ipmi_log(ipmi_log_path, fig_ipmi, ax_ipmi, ipmi_graph_path)
        except Exception as e:
            print(f"⚠️ 시각화 오류: {e}")

        elapsed = time.time() - start
        sleep_time = max(0, interval_sec - elapsed)
        time.sleep(sleep_time)




# -------------------------- 실행 시작 --------------------------
print("🚀 부하 테스트 시작")

stop_logging = threading.Event()

log_threads = [
    threading.Thread(target=log_gpu, args=(0, gpu_log_path_0)),
    threading.Thread(target=log_gpu, args=(1, gpu_log_path_1)),
    threading.Thread(target=log_temp),
    threading.Thread(target=log_ipmi_power)
]
for t in log_threads:
    t.start()

burn_threads = [
    threading.Thread(target=run_gpu_burn, args=(0,)),
    threading.Thread(target=run_gpu_burn, args=(1,)),
    threading.Thread(target=run_stress_ng)
]
for t in burn_threads:
    t.start()

visual_thread = threading.Thread(target=periodic_visualization, args=(30, args.total_duration))
visual_thread.start()

time.sleep(args.total_duration)
stop_logging.set()

for t in log_threads + burn_threads + [visual_thread]:
    t.join()

print("✅ 전체 테스트 및 분석 완료.")
