import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import math
import time
import os # For checking DM_CAN.py existence
import serial

# Attempt to import DM_CAN components
try:
    from DM_CAN import Motor, MotorControl, DM_Motor_Type, Control_Type, DM_variable
except ImportError:
    # This messagebox might not show if Tkinter root isn't properly initiated yet,
    # but the check in __main__ will handle it.
    print("ERROR: DM_CAN.py not found or cannot be imported. Place it in the same directory.")
    # messagebox.showerror("Dependency Error", "DM_CAN.py not found. Please place it in the same directory as this script.")
    # exit() # exit() here might be too abrupt before Tkinter fully starts

# --- Default Configuration ---
DEFAULT_SERIAL_PORT = '/dev/tty.usbmodem00000000050C1' # Adjust for your OS/device
DEFAULT_BAUD_RATE = 921600
DEFAULT_MOTOR_TYPE = DM_Motor_Type.DM4310

# Speed Slider Configuration
SLIDER_MAX_RPM = 250
SLIDER_MIN_RPM = -250

class MotorControlApp:
    def __init__(self, root_window):
        self.root = root_window
        self.root.title("Motor Speed Controller")
        self.root.geometry("550x600") # Increased window size

        self.motor = None
        self.motor_controller = None
        self.serial_device = None
        self.is_motor_connected = False # Tracks if initial connection and mode switch were successful
        self.is_motor_enabled = False
        self.current_target_rpm = 0.0
        
        self.initial_can_id = tk.StringVar(value="1") # Default initial CAN ID (e.g., 0x01)
        self.initial_master_id = tk.StringVar(value="17")# Default initial Master ID (e.g., 0x11)

        # --- UI Frames ---
        connection_frame = ttk.LabelFrame(self.root, text="1. Motor Connection")
        connection_frame.pack(padx=10, pady=10, fill="x")

        id_management_frame = ttk.LabelFrame(self.root, text="2. ID Management")
        id_management_frame.pack(padx=10, pady=5, fill="x")
        
        control_frame = ttk.LabelFrame(self.root, text="3. Motor Control")
        control_frame.pack(padx=10, pady=5, fill="x")

        # --- 1. Connection Frame Widgets ---
        ttk.Label(connection_frame, text="Serial Port:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.serial_port_entry = ttk.Entry(connection_frame, width=30)
        self.serial_port_entry.insert(0, DEFAULT_SERIAL_PORT)
        self.serial_port_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(connection_frame, text="Initial CAN ID (1-127):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.can_id_entry = ttk.Entry(connection_frame, textvariable=self.initial_can_id, width=10)
        self.can_id_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(connection_frame, text="Initial Master ID (Host):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.master_id_entry = ttk.Entry(connection_frame, textvariable=self.initial_master_id, width=10)
        self.master_id_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        self.connect_button = ttk.Button(connection_frame, text="Connect & Setup Motor", command=self.setup_motor_communication)
        self.connect_button.grid(row=3, column=0, columnspan=2, padx=5, pady=10)

        # --- Status Label (Global) ---
        self.status_label = ttk.Label(self.root, text="Status: Disconnected", foreground="blue", font=("Arial", 10))
        self.status_label.pack(pady=5)

        # --- 2. ID Management Frame Widgets ---
        ttk.Label(id_management_frame, text="New CAN ID (1-127):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.new_can_id_entry = ttk.Entry(id_management_frame, width=10)
        self.new_can_id_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.set_can_id_button = ttk.Button(id_management_frame, text="Set New CAN ID", command=self.set_new_can_id_action, state=tk.DISABLED)
        self.set_can_id_button.grid(row=0, column=2, padx=5, pady=5)

        ttk.Label(id_management_frame, text="Motor's Master ID (MST_ID):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.motor_master_id_display = ttk.Label(id_management_frame, text="N/A", font=("Arial", 10, "bold"))
        self.motor_master_id_display.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self.read_master_id_button = ttk.Button(id_management_frame, text="Read Motor's Master ID", command=self.read_motor_master_id_action, state=tk.DISABLED)
        self.read_master_id_button.grid(row=1, column=2, padx=5, pady=5)

        # --- 3. Control Frame Widgets ---
        self.enable_button_text = tk.StringVar(value="Enable Motor")
        self.enable_button = ttk.Button(control_frame, textvariable=self.enable_button_text, command=self.toggle_motor_enable, state=tk.DISABLED)
        self.enable_button.pack(pady=10)

        self.rpm_display_label = ttk.Label(control_frame, text=f"Target Speed: {self.current_target_rpm:.1f} RPM (0.00 rad/s)")
        self.rpm_display_label.pack(pady=5)

        self.speed_scale = ttk.Scale(control_frame, from_=SLIDER_MIN_RPM, to=SLIDER_MAX_RPM, orient=tk.HORIZONTAL, length=350, command=self.on_speed_scale_change, state=tk.DISABLED)
        self.speed_scale.set(0)
        self.speed_scale.pack(pady=10)

        self.stop_button = ttk.Button(control_frame, text="Send Zero Speed", command=self.send_zero_speed, state=tk.DISABLED)
        self.stop_button.pack(pady=5)
        
        # --- Quit Button (Global) ---
        self.quit_button = ttk.Button(self.root, text="Quit", command=self.quit_application)
        self.quit_button.pack(pady=10, side=tk.BOTTOM)

        self.root.protocol("WM_DELETE_WINDOW", self.quit_application)


    def update_status_label(self, message, color="black"):
        self.status_label.config(text=f"Status: {message}", foreground=color)

    def _get_int_id_from_entry(self, entry_var, id_name="ID"):
        try:
            val_str = entry_var.get()
            if val_str.lower().startswith('0x'):
                return int(val_str, 16)
            return int(val_str)
        except ValueError:
            messagebox.showerror("Input Error", f"Invalid {id_name}. Please enter a valid integer (e.g., 1) or hex (e.g., 0x01).")
            return None

    def setup_motor_communication(self):
        if self.is_motor_connected:
            messagebox.showinfo("Info", "Motor already connected and set up. Disconnect first if you want to re-initialize.")
            return

        can_id = self._get_int_id_from_entry(self.initial_can_id, "Initial CAN ID")
        if can_id is None: return
        
        master_id_for_constructor = self._get_int_id_from_entry(self.initial_master_id, "Initial Master ID (Host)")
        if master_id_for_constructor is None: return

        port = self.serial_port_entry.get()

        try:
            self.update_status_label(f"Connecting to Motor (ID {can_id}) on {port}...", "orange")
            self.root.update_idletasks() # Force GUI update

            self.motor = Motor(DEFAULT_MOTOR_TYPE, can_id, master_id_for_constructor)
            print(f"Motor object created: CAN ID 0x{can_id:02X}, Initial Master ID 0x{master_id_for_constructor:02X}")

            self.serial_device = serial.Serial(port, DEFAULT_BAUD_RATE, timeout=0.5)
            
            self.motor_controller = MotorControl(self.serial_device) # This opens the serial port
            self.motor_controller.addMotor(self.motor)
            print(f"Motor 0x{can_id:02X} added to controller.")

            print(f"Switching Motor 0x{can_id:02X} to VEL mode...")
            switch_mode_result = self.motor_controller.switchControlMode(self.motor, Control_Type.VEL)
            print(f"switchControlMode result: {switch_mode_result}")

            if not switch_mode_result:
                raise Exception(f"Failed to switch to VEL mode (Result: {switch_mode_result}). Check motor connection & ID.")

            self.is_motor_connected = True
            self.is_motor_enabled = False # Motor is setup, but not enabled yet
            self.update_status_label(f"Connected to Motor ID {can_id}. Mode: VEL. Disabled.", "green")
            self.enable_button.config(state=tk.NORMAL)
            self.set_can_id_button.config(state=tk.NORMAL)
            self.read_master_id_button.config(state=tk.NORMAL)
            self.connect_button.config(text="Disconnect Motor", command=self.disconnect_motor_communication)


        except serial.SerialException as e:
            self.is_motor_connected = False
            messagebox.showerror("Serial Error", f"Failed to open/config port {port}.\nError: {e}")
            self.update_status_label(f"Serial Error on {port}", "red")
        except Exception as e:
            self.is_motor_connected = False
            messagebox.showerror("Setup Error", f"Motor setup failed.\nError: {e}")
            self.update_status_label(f"Motor Setup Error: {e}", "red")
            if self.serial_device and self.serial_device.is_open:
                 self.serial_device.close()
        finally:
            if not self.is_motor_connected:
                self.connect_button.config(text="Connect & Setup Motor", command=self.setup_motor_communication)


    def disconnect_motor_communication(self):
        if self.is_motor_enabled:
            self._disable_motor_action() # Try to disable gracefully

        if self.serial_device and self.serial_device.is_open:
            self.serial_device.close()
            print("Serial port closed.")
        
        self.is_motor_connected = False
        self.is_motor_enabled = False
        self.motor = None
        self.motor_controller = None

        self.update_status_label("Disconnected", "blue")
        self.enable_button.config(state=tk.DISABLED)
        self.speed_scale.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        self.set_can_id_button.config(state=tk.DISABLED)
        self.read_master_id_button.config(state=tk.DISABLED)
        self.motor_master_id_display.config(text="N/A")
        self.enable_button_text.set("Enable Motor")
        self.speed_scale.set(0)
        self.on_speed_scale_change("0")
        self.connect_button.config(text="Connect & Setup Motor", command=self.setup_motor_communication)
        print("Motor disconnected.")

    def _enable_motor_action(self):
        print("Enabling motor...")
        self.motor_controller.enable(self.motor)
        time.sleep(0.2) # Allow time for enable
        self.is_motor_enabled = True
        self.enable_button_text.set("Disable Motor")
        self.speed_scale.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)
        self.update_status_label(f"Motor ID {self.motor.SlaveID} Enabled. Speed: {self.current_target_rpm:.1f} RPM", "green")
        print("Motor enabled.")
        
    def _disable_motor_action(self):
        print("Disabling motor...")
        self.motor_controller.control_Vel(self.motor, 0) # Stop first
        time.sleep(0.05)
        self.motor_controller.disable(self.motor)
        self.is_motor_enabled = False
        self.enable_button_text.set("Enable Motor")
        self.speed_scale.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        self.speed_scale.set(0)
        self.on_speed_scale_change("0") # Update display
        self.update_status_label(f"Motor ID {self.motor.SlaveID} Disabled.", "blue")
        print("Motor disabled.")

    def toggle_motor_enable(self):
        if not self.is_motor_connected:
            messagebox.showwarning("Warning", "Motor not connected or setup.")
            return
        try:
            if self.is_motor_enabled:
                self._disable_motor_action()
            else:
                self._enable_motor_action()
        except Exception as e:
            messagebox.showerror("Error", f"Enable/Disable action failed: {e}")
            self.update_status_label(f"Enable/Disable Error: {e}", "red")

    def on_speed_scale_change(self, rpm_str_value):
        if not self.is_motor_connected:
            return
        try:
            target_rpm = float(rpm_str_value)
            self.current_target_rpm = target_rpm
            target_rad_per_sec = target_rpm * (2 * math.pi) / 60.0
            self.rpm_display_label.config(text=f"Target Speed: {target_rpm:.1f} RPM ({target_rad_per_sec:.2f} rad/s)")

            if self.is_motor_enabled:
                self.motor_controller.control_Vel(self.motor, target_rad_per_sec)
                self.update_status_label(f"Motor ID {self.motor.SlaveID} Enabled. Speed: {target_rpm:.1f} RPM", "green")
        except Exception as e:
            # print(f"Scale callback error: {e}") # Avoid flooding console
            self.update_status_label(f"Speed Set Error: {e}", "red")

    def send_zero_speed(self):
        if not self.is_motor_connected or not self.is_motor_enabled :
            messagebox.showwarning("Warning", "Motor not connected or not enabled.")
            return
        print("Sending Zero Speed command...")
        self.speed_scale.set(0) # This will trigger on_speed_scale_change

    def read_motor_master_id_action(self):
        if not self.is_motor_connected:
            messagebox.showwarning("Warning", "Motor not connected.")
            return
        try:
            self.update_status_label(f"Reading Master ID for Motor {self.motor.SlaveID}...", "orange")
            self.root.update_idletasks()
            master_id_val = self.motor_controller.read_motor_param(self.motor, DM_variable.MST_ID)
            if master_id_val is not None:
                self.motor_master_id_display.config(text=f"{master_id_val} (0x{master_id_val:02X})")
                self.update_status_label(f"Motor {self.motor.SlaveID}: Master ID is {master_id_val}.", "black")
                messagebox.showinfo("Master ID Read", f"Motor's configured Master ID (MST_ID): {master_id_val} (0x{master_id_val:02X})")
            else:
                self.motor_master_id_display.config(text="Read Failed")
                self.update_status_label(f"Failed to read Master ID for Motor {self.motor.SlaveID}.", "red")
                messagebox.showerror("Read Error", "Failed to read Master ID from motor.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read Master ID: {e}")
            self.update_status_label(f"Read Master ID Error: {e}", "red")
            self.motor_master_id_display.config(text="Error")


    def set_new_can_id_action(self):
        if not self.is_motor_connected:
            messagebox.showwarning("Warning", "Motor not connected.")
            return

        try:
            new_can_id_str = self.new_can_id_entry.get()
            if not new_can_id_str:
                messagebox.showerror("Input Error", "New CAN ID cannot be empty.")
                return
            
            if new_can_id_str.lower().startswith('0x'):
                new_can_id = int(new_can_id_str, 16)
            else:
                new_can_id = int(new_can_id_str)

            if not (0 < new_can_id < 128): # Typical CAN ID range
                messagebox.showerror("Input Error", "New CAN ID must be between 1 and 127.")
                return
            
            if new_can_id == self.motor.SlaveID:
                messagebox.showinfo("Info", "New CAN ID is the same as the current CAN ID.")
                return

        except ValueError:
            messagebox.showerror("Input Error", "Invalid New CAN ID. Please enter an integer (e.g., 2) or hex (e.g., 0x02).")
            return

        if not messagebox.askyesno("Confirm CAN ID Change", 
                                   f"This will attempt to change the motor's CAN ID from {self.motor.SlaveID} to {new_can_id}.\n"
                                   "The motor's parameters should be saved for this change to be permanent.\n"
                                   "After this, you will need to reconnect to the motor using the NEW ID: {new_can_id}.\n\nProceed?"):
            return

        try:
            old_can_id = self.motor.SlaveID
            self.update_status_label(f"Setting CAN ID for motor {old_can_id} to {new_can_id}...", "orange")
            self.root.update_idletasks()

            # Temporarily disable motor if enabled
            was_enabled = self.is_motor_enabled
            if was_enabled:
                self._disable_motor_action()
                time.sleep(0.1) # ensure it's disabled

            # Change CAN ID parameter (ESC_ID = 8)
            print(f"Calling change_motor_param with RID: DM_variable.ESC_ID ({DM_variable.ESC_ID}), Data: {new_can_id}")
            success = self.motor_controller.change_motor_param(self.motor, DM_variable.ESC_ID, new_can_id)
            print(f"change_motor_param for ESC_ID result: {success}")

            if success:
                messagebox.showinfo("CAN ID Set (Volatile)", 
                                    f"CAN ID parameter set to {new_can_id} in motor's volatile memory.\n"
                                    "To make this permanent, parameters MUST BE SAVED to the motor's flash memory.\n"
                                    "Attempting to save now...")
                
                self.update_status_label(f"Saving parameters for new CAN ID {new_can_id}...", "orange")
                self.root.update_idletasks()
                
                # save_motor_param in DM_CAN.py already disables the motor
                self.motor_controller.save_motor_param(self.motor) # This uses the OLD CAN ID for addressing during save
                time.sleep(0.2) # Allow save to complete
                
                self.update_status_label(f"CAN ID changed to {new_can_id} and saved. Disconnecting.", "green")
                messagebox.showinfo("CAN ID Changed & Saved",
                                    f"Motor CAN ID successfully changed to {new_can_id} and parameters saved.\n"
                                    "The application will now disconnect from the old ID.\n"
                                    f"Please use the new CAN ID ({new_can_id}) to reconnect.")
                
                # Disconnect as the current motor object and controller map are for the old ID
                self.disconnect_motor_communication()
                self.initial_can_id.set(str(new_can_id)) # Pre-fill new CAN ID for next connection
                self.new_can_id_entry.delete(0, tk.END) # Clear the entry

            else:
                messagebox.showerror("Error", f"Failed to set new CAN ID {new_can_id} on motor {old_can_id}.")
                self.update_status_label(f"Failed to set CAN ID {new_can_id}.", "red")
                # If it failed but motor was previously enabled, try to re-enable with old ID logic
                if was_enabled and self.is_motor_connected and not self.is_motor_enabled:
                    try:
                        self._enable_motor_action()
                    except Exception: pass # Best effort

        except Exception as e:
            messagebox.showerror("Error", f"Failed to set new CAN ID: {e}")
            self.update_status_label(f"Set CAN ID Error: {e}", "red")


    def quit_application(self):
        print("Quitting application...")
        self.disconnect_motor_communication() # Try to clean up
        self.root.destroy()
        print("Application quit.")


if __name__ == "__main__":
    if not os.path.exists("DM_CAN.py"):
        # This Tkinter setup is just to show the error if DM_CAN.py is missing
        root_err = tk.Tk()
        root_err.withdraw() # Hide the main window
        messagebox.showerror("Dependency Error", "DM_CAN.py not found.\nPlease ensure DM_CAN.py is in the same directory as this script.")
        root_err.destroy()
    else:
        try:
            # Check if DM_CAN was imported successfully earlier
            Motor # Just to see if it's defined
        except NameError:
            root_err = tk.Tk()
            root_err.withdraw()
            messagebox.showerror("Import Error", "Failed to import necessary components from DM_CAN.py.\nCheck for errors in DM_CAN.py or its dependencies (like numpy).")
            root_err.destroy()
        else:
            root_main = tk.Tk()
            app = MotorControlApp(root_main)
            root_main.mainloop()