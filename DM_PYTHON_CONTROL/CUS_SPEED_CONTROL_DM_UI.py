import tkinter as tk
from tkinter import ttk  # For themed widgets, like a nicer Scale
from tkinter import messagebox
import math
import time # For potential delays, though GUI should avoid long sleeps in main thread
import serial

# DM_CAN.py (包含 Motor, MotorControl, DM_Motor_Type, Control_Type, DM_variable 等)
# 应该与此脚本在同一目录下，或已安装
try:
    from DM_CAN import Motor, MotorControl, DM_Motor_Type, Control_Type, DM_variable
except ImportError:
    messagebox.showerror("错误", "DM_CAN.py 未找到或无法导入。\n请确保它和脚本在同一目录。")
    exit()


# --- 电机和串口配置 ---
SERIAL_PORT = '/dev/tty.usbmodem00000000050C1'  # Mac上的串口路径示例
BAUD_RATE = 921600
MOTOR_CAN_ID = 0x01
MOTOR_MASTER_ID = 0x11
MOTOR_TYPE = DM_Motor_Type.DM4310 # 根据DM_CAN.py, DM4310是类型0

# 速度限制 (根据 DM4310 DQ_MAX = 30 rad/s)
# 30 rad/s approx 286 RPM. 我们设置滑块范围为 +/- 250 RPM
SLIDER_MAX_RPM = 250
SLIDER_MIN_RPM = -250

class MotorControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("达妙电机调速器 (DM_CAN)")
        self.root.geometry("450x350") # 调整窗口大小

        self.motor = None
        self.motor_controller = None
        self.serial_device = None
        self.is_motor_setup_successful = False
        self.is_motor_enabled = False
        self.current_target_rpm = 0.0

        # --- 初始化电机和串口 ---
        if not self.setup_motor_communication():
            # 如果设置失败，GUI仍会显示，但功能受限
            pass

        # --- GUI 控件 ---
        # 状态标签
        self.status_label = tk.Label(root, text="状态: 未初始化", fg="blue", height=2, font=("Arial", 10))
        self.status_label.pack(pady=10)

        # 使能/失能按钮
        self.enable_button_text = tk.StringVar(value="使能电机 (Enable)")
        self.enable_button = tk.Button(root, textvariable=self.enable_button_text, command=self.toggle_motor_enable, width=20, height=2, font=("Arial", 12))
        self.enable_button.pack(pady=10)
        if not self.is_motor_setup_successful:
            self.enable_button.config(state=tk.DISABLED)


        # RPM 显示标签
        self.rpm_display_label = tk.Label(root, text=f"目标转速: {self.current_target_rpm:.1f} RPM (0.00 rad/s)", font=("Arial", 11))
        self.rpm_display_label.pack(pady=5)

        # 速度控制滑块 (Scale)
        self.speed_scale = ttk.Scale(root, from_=SLIDER_MIN_RPM, to=SLIDER_MAX_RPM, orient=tk.HORIZONTAL, length=300, command=self.on_speed_scale_change)
        self.speed_scale.set(0) # 初始值
        self.speed_scale.pack(pady=10)
        if not self.is_motor_setup_successful or not self.is_motor_enabled:
             self.speed_scale.config(state=tk.DISABLED)


        # 停止按钮（发送0速度）
        self.stop_button = tk.Button(root, text="发送0转速 (Stop)", command=self.send_zero_speed, width=15, height=2, font=("Arial", 10))
        self.stop_button.pack(pady=5)
        if not self.is_motor_setup_successful or not self.is_motor_enabled:
            self.stop_button.config(state=tk.DISABLED)

        # 退出按钮
        self.quit_button = tk.Button(root, text="退出 (Quit)", command=self.quit_application, width=10, font=("Arial", 10))
        self.quit_button.pack(pady=10, side=tk.BOTTOM)

        self.root.protocol("WM_DELETE_WINDOW", self.quit_application) # 处理窗口关闭事件

        # 初始状态更新
        if self.is_motor_setup_successful:
             self.update_status_label("状态: 初始化成功, 电机已失能", "green")
        else:
             self.update_status_label("状态: 初始化失败, 请检查连接或配置", "red")


    def update_status_label(self, message, color="black"):
        self.status_label.config(text=message, fg=color)

    def setup_motor_communication(self):
        try:
            self.motor = Motor(MOTOR_TYPE, MOTOR_CAN_ID, MOTOR_MASTER_ID)
            print(f"电机对象创建: CAN ID 0x{MOTOR_CAN_ID:02X}")

            self.serial_device = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.5)
            # DM_CAN.py 的 MotorControl.__init__ 会自行处理串口的 open/close
            # print(f"串口 {SERIAL_PORT} 准备就绪")

            self.motor_controller = MotorControl(self.serial_device)
            self.motor_controller.addMotor(self.motor)
            print(f"电机 0x{MOTOR_CAN_ID:02X} 已添加到控制器")

            print(f"尝试切换电机 0x{MOTOR_CAN_ID:02X} 到 VEL (纯速度) 模式...")
            # 注意: DM_CAN.py 中的 switchControlMode 是阻塞的，并且有内部延时和重试
            # 在GUI启动时执行此操作可能会导致短暂的无响应
            switch_mode_result = self.motor_controller.switchControlMode(self.motor, Control_Type.VEL)
            print(f"switchControlMode 返回: {switch_mode_result}")

            if not switch_mode_result: # 假设 DM_CAN 返回 True 表示成功
                messagebox.showerror("初始化错误", f"电机模式切换到VEL失败 (返回: {switch_mode_result})。\n请检查电机连接和配置。")
                if self.serial_device and self.serial_device.is_open:
                    self.serial_device.close()
                return False

            print("电机模式切换成功。")
            self.is_motor_setup_successful = True
            return True

        except serial.SerialException as e:
            messagebox.showerror("串口错误", f"无法打开或配置串口 {SERIAL_PORT}。\n错误: {e}\n请检查设备连接和端口号。")
            self.is_motor_setup_successful = False
            return False
        except Exception as e:
            messagebox.showerror("初始化错误", f"电机初始化过程中发生未知错误。\n错误: {e}")
            self.is_motor_setup_successful = False
            if self.serial_device and self.serial_device.is_open:
                 self.serial_device.close() # 尝试关闭
            return False

    def toggle_motor_enable(self):
        if not self.is_motor_setup_successful:
            messagebox.showwarning("警告", "电机通信未成功初始化。")
            return

        # 注意: enable/disable 也是阻塞的，GUI会短暂卡顿
        if self.is_motor_enabled:
            # --- 失能电机 ---
            try:
                print("尝试发送0速度并失能电机...")
                self.motor_controller.control_Vel(self.motor, 0) # 先停止
                time.sleep(0.05) # 给停止指令一点时间
                self.motor_controller.disable(self.motor)
                self.is_motor_enabled = False
                self.enable_button_text.set("使能电机 (Enable)")
                self.update_status_label("状态: 电机已失能", "blue")
                self.speed_scale.set(0) # 滑块归零
                self.on_speed_scale_change(0) # 更新显示
                self.speed_scale.config(state=tk.DISABLED)
                self.stop_button.config(state=tk.DISABLED)
                print("电机已失能。")
            except Exception as e:
                messagebox.showerror("错误", f"失能电机时出错: {e}")
                self.update_status_label(f"错误: 失能失败 - {e}", "red")
        else:
            # --- 使能电机 ---
            try:
                print("尝试使能电机...")
                self.motor_controller.enable(self.motor)
                # enable 函数在 DM_CAN.py 中有0.1s的延时和recv
                # 我们额外加一点延时确保状态稳定
                time.sleep(0.2) # 等待使能完成
                self.is_motor_enabled = True
                self.enable_button_text.set("失能电机 (Disable)")
                self.update_status_label("状态: 电机已使能, 速度: 0 RPM", "green")
                self.speed_scale.config(state=tk.NORMAL)
                self.stop_button.config(state=tk.NORMAL)
                print("电机已使能。")
            except Exception as e:
                messagebox.showerror("错误", f"使能电机时出错: {e}")
                self.update_status_label(f"错误: 使能失败 - {e}", "red")


    def on_speed_scale_change(self, rpm_str_value):
        if not self.is_motor_setup_successful:
            return

        try:
            target_rpm = float(rpm_str_value)
            self.current_target_rpm = target_rpm

            # RPM to rad/s
            target_rad_per_sec = target_rpm * (2 * math.pi) / 60.0

            self.rpm_display_label.config(text=f"目标转速: {target_rpm:.1f} RPM ({target_rad_per_sec:.2f} rad/s)")

            if self.is_motor_enabled:
                # 注意: control_Vel 也是阻塞的，但如果其内部recv很快，可能不明显
                self.motor_controller.control_Vel(self.motor, target_rad_per_sec)
                # print(f"发送速度指令: {target_rad_per_sec:.2f} rad/s") # 频繁打印会影响性能
                # 更新状态标签中的速度
                self.update_status_label(f"状态: 电机已使能, 速度: {target_rpm:.1f} RPM", "green")
            # else:
                # print("电机未使能，仅更新滑块值。")

        except Exception as e:
            print(f"滑块回调中发生错误: {e}")
            # 不在滑块回调中显示messagebox，避免过于频繁
            self.update_status_label(f"错误: 速度设置失败 - {e}", "red")


    def send_zero_speed(self):
        if not self.is_motor_setup_successful:
            messagebox.showwarning("警告", "电机通信未成功初始化。")
            return
        if not self.is_motor_enabled:
            messagebox.showinfo("提示", "电机未使能。")
            return

        print("发送0速度指令...")
        self.speed_scale.set(0) # 移动滑块到0，会触发 on_speed_scale_change
        # on_speed_scale_change(0) 会处理发送0速度的逻辑和标签更新


    def quit_application(self):
        print("正在退出应用程序...")
        if self.is_motor_setup_successful and self.motor_controller and self.motor:
            if self.is_motor_enabled:
                try:
                    print("尝试停止并失能电机...")
                    self.motor_controller.control_Vel(self.motor, 0)
                    time.sleep(0.1) # 等待指令
                    self.motor_controller.disable(self.motor)
                    print("电机已失能。")
                except Exception as e:
                    print(f"退出时失能电机出错: {e}")
        
        if self.serial_device and self.serial_device.is_open:
            self.serial_device.close()
            print("串口已关闭。")
        
        self.root.destroy()
        print("应用程序已退出。")


if __name__ == "__main__":
    # 检查 DM_CAN.py 是否存在 (基本检查)
    import os
    if not os.path.exists("DM_CAN.py"):
        root_check = tk.Tk()
        root_check.withdraw() # 隐藏主窗口，只显示消息框
        messagebox.showerror("依赖文件错误", "DM_CAN.py 文件未在本目录找到。\n请确保该文件存在。")
        root_check.destroy()
    else:
        root = tk.Tk()
        app = MotorControlApp(root)
        root.mainloop()