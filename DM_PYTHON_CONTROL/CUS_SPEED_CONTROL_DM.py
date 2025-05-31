import math
from DM_CAN import * # 假设 DM_CAN.py 与此脚本在同一目录或已安装
import serial
import time

# --- 初始化单个电机 (使用原 Motor1 的参数，但改为速度模式) ---
MOTOR_CAN_ID = 0x01
MOTOR_MASTER_ID = 0x11
# MOTOR_TYPE = DM_Motor_Type.DM4310 # 已在 DM_CAN.py 中定义，这里只是注释说明
# 从 DM_CAN.py 中我们知道 DM_Motor_Type.DM4310 对应的值是 0
# Motor 类构造函数第一个参数是 MotorType，可以直接传 DM_Motor_Type.DM4310
motor = Motor(DM_Motor_Type.DM4310, MOTOR_CAN_ID, MOTOR_MASTER_ID)
print(f"单个电机初始化: CAN ID 0x{MOTOR_CAN_ID:02X}, Master ID 0x{MOTOR_MASTER_ID:02X}")

# --- 串口和电机控制器初始化 ---
# 请确保这里的串口号和波特率是正确的
serial_port_name = '/dev/tty.usbmodem00000000050C1' # Mac上的串口路径示例
baud_rate = 921600 # 根据DM_CAN.py中的默认帧结构，这可能不是串口波特率，而是USB转CAN模块的内部速率或配置。
                   # DM_CAN.py 中的 MotorControl 类并没有设置串口波特率，它期望 serial_device 已经配置好了。
                   # 我们脚本的 serial.Serial() 调用中设置的才是实际的 Mac 到 USB转CAN适配器的串口通信波特率。

serial_device = serial.Serial(serial_port_name, baud_rate, timeout=0.5)
# DM_CAN.py 中的 MotorControl __init__ 会先关闭再打开串口，所以这里我们确保它在传入前是打开的
# if not serial_device.is_open:
#     serial_device.open()
# print(f"串口 {serial_port_name} 已打开，波特率 {baud_rate}") # MotorControl内部会打印

motor_controller = MotorControl(serial_device)
motor_controller.addMotor(motor) # 添加单个电机到控制器
print(f"电机 CAN ID 0x{MOTOR_CAN_ID:02X} 已添加到控制器")

# --- 设置电机为纯速度模式 (VEL) ---
print(f"尝试设置电机 CAN ID 0x{MOTOR_CAN_ID:02X} 为 VEL (纯速度) 模式...")
switch_mode_success = motor_controller.switchControlMode(motor, Control_Type.VEL)
print(f"switchControlMode 返回: {switch_mode_success}") # 打印实际返回值

if switch_mode_success: # 假设 DM_CAN 返回 True 表示成功
    print(f"电机 CAN ID 0x{MOTOR_CAN_ID:02X} 切换到 VEL 模式成功")
else:
    print(f"警告: 电机 CAN ID 0x{MOTOR_CAN_ID:02X} 切换到 VEL 模式失败!")
    if serial_device.is_open:
        serial_device.close()
    exit()

# --- 读取电机参数 (这些参数在速度模式下也可能有用) ---
print(f"--- 读取电机 CAN ID 0x{MOTOR_CAN_ID:02X} 的参数 ---")
try:
    # 注意：DM_CAN.py 中的 read_motor_param 是阻塞的，并且依赖 recv_set_param_data
    # 它内部有重试和延时，所以调用会花一些时间。
    print(f"  sub_ver: {motor_controller.read_motor_param(motor, DM_variable.sub_ver)}")
    print(f"  Gr (减速比): {motor_controller.read_motor_param(motor, DM_variable.Gr)}")
    # PMAX 在纯速度模式下可能不直接使用，但VMAX和TMAX仍然相关
    print(f"  PMAX (位置幅值): {motor_controller.read_motor_param(motor, DM_variable.PMAX)}")
    print(f"  MST_ID (主机ID): {motor_controller.read_motor_param(motor, DM_variable.MST_ID)}")
    print(f"  VMAX (速度幅值): {motor_controller.read_motor_param(motor, DM_variable.VMAX)}")
    print(f"  TMAX (力矩幅值): {motor_controller.read_motor_param(motor, DM_variable.TMAX)}")
except Exception as e:
    print(f"读取电机参数时发生错误: {e}")


# --- 保存电机参数 (如果需要将模式等设置持久化) ---
# print(f"尝试保存电机 CAN ID 0x{MOTOR_CAN_ID:02X} 的参数...")
# if motor_controller.save_motor_param(motor): # save_motor_param 内部会先disable电机
#     print(f"电机 CAN ID 0x{MOTOR_CAN_ID:02X} 参数保存成功。")
# else:
#     print(f"警告: 电机 CAN ID 0x{MOTOR_CAN_ID:02X} 参数保存失败。")
# # 如果执行了保存，电机可能被禁用了，需要重新使能（或者修改save_motor_param不禁用）
# # 为简单起见，如果取消注释保存，确保下面有使能步骤


# --- 使能电机 ---
print(f"尝试使能电机 CAN ID 0x{MOTOR_CAN_ID:02X}...")
motor_controller.enable(motor) # enable本身有0.1秒延时和recv
# DM_CAN.py中的enable没有明确的成功/失败返回值，我们假设调用即尝试。
# 为了确认状态，可能需要读取某个状态参数，或者依赖后续操作是否成功。
# 暂时我们先认为调用后，过一段时间电机即为使能状态。
# 实际应用中，最好有一个确认使能状态的方法。
print(f"已发送使能指令到电机 CAN ID 0x{MOTOR_CAN_ID:02X}。等待短暂时间确保使能...")
time.sleep(0.5) # 给电机一点时间响应使能指令

# --- 控制循环 ---
print("进入控制循环 (纯速度模式)...")
i = 0
max_iterations = 10000
try:
    while i < max_iterations:
        q = math.sin(time.time()) # q 值在 -1 到 1 之间变化
        i = i + 1

        # 控制单个电机 (纯速度模式)
        # 目标速度 8*q rad/s (与原脚本中对Motor2的动态速度指令类似)
        target_velocity_rad_s = 8 * q
        motor_controller.control_Vel(motor, target_velocity_rad_s)

        # 如果需要获取和打印电机状态
        # 注意：getPosition() 在纯速度模式下返回的是累计位置或编码器原始值
        # state_dq 和 state_tau 会在 control_Vel 调用内部的 recv() 后被更新
        # 但Motor对象的属性需要通过 getVelocity() 等方法访问
        # control_Vel本身调用了recv, 所以电机状态应该会更新
        if i % 200 == 0: #降低打印频率
            # motor_controller.refresh_motor_status(motor) # 如果需要主动刷新状态
            # time.sleep(0.01) # 给刷新一点时间
            current_vel_feedback = motor.getVelocity() # 获取通过recv更新的状态
            current_torque_feedback = motor.getTorque()
            print(f"Iter: {i}, TargetVel: {target_velocity_rad_s:.2f} rad/s, FeedbackVel: {current_vel_feedback:.2f} rad/s, Torque: {current_torque_feedback:.2f} Nm")


        time.sleep(0.001) # 循环延时

except KeyboardInterrupt:
    print("\n捕获到Ctrl+C，准备停止电机并退出...")
except Exception as e:
    print(f"控制循环中发生错误: {e}")
finally:
    # --- 语句结束，停止电机并关闭串口 ---
    print("控制循环结束或发生异常。")
    print(f"尝试停止电机 CAN ID 0x{MOTOR_CAN_ID:02X}...")
    try:
        motor_controller.control_Vel(motor, 0) # 发送零速度指令
        print(f"已发送0速度指令到电机 CAN ID 0x{MOTOR_CAN_ID:02X}。")
        time.sleep(0.2) # 等待指令生效和电机响应
        motor_controller.disable(motor) # 禁用电机
        print(f"电机 CAN ID 0x{MOTOR_CAN_ID:02X} 已禁用。")
    except Exception as e_stop:
        print(f"停止电机时发生错误: {e_stop}")

    if serial_device.is_open:
        serial_device.close()
        print("串口已关闭。")
    print("程序已退出。")