import serial
import serial.tools.list_ports
import threading
import time
import random
import math
import tkinter as tk
from tkinter import ttk, messagebox
import sys

TOTAL_BITS_SENT = 0
TOTAL_BITS_RECEIVED = 0
TOTAL_BITS_ERROR = 0

class PRBS_Generator:
    """PRBS-7, PRBS-15 ve PRBS-23 için Pseudo-Random Binary Sequence üreticisi."""
    POLYNOMIALS = {
        7: (7, [6]),
        15: (15, [14]),
        23: (23, [18])
    }

    def __init__(self, prbs_length):
        self.length = prbs_length
        self.taps = self.POLYNOMIALS.get(prbs_length)
        if not self.taps:
            raise ValueError(f"PRBS-{prbs_length} desteklenmiyor.")
        self.register = (1 << self.length) - 1

    def get_next_bit(self):
        new_bit = 0
        for tap in self.taps[1]:
            new_bit ^= (self.register >> tap) & 1
        output_bit = self.register & 1
        self.register = (self.register >> 1) | (new_bit << (self.length - 1))
        return output_bit

def generate_prbs_data(size_bytes, prbs_gen):
    data = bytearray()
    current_byte = 0
    bit_count = 0
    for _ in range(size_bytes * 8):
        bit = prbs_gen.get_next_bit()
        bit_pos = bit_count % 8
        current_byte |= (bit << bit_pos)
        
        if bit_pos == 7:
            data.append(current_byte)
            current_byte = 0
        bit_count += 1
    
    if bit_count % 8 != 0:
         data.append(current_byte)

    return bytes(data)

def generate_random_data(size):
    return bytes([random.randint(0, 255) for _ in range(size)])

def calculate_bit_errors(original_data, received_data):
    global TOTAL_BITS_ERROR
    bit_errors = 0
    min_len = min(len(original_data), len(received_data))
    
    for i in range(min_len):
        xor_result = original_data[i] ^ received_data[i]
        bit_errors += bin(xor_result).count('1')
    
    if len(original_data) != len(received_data):
        bit_errors += abs(len(original_data) - len(received_data)) * 8
        
    TOTAL_BITS_ERROR += bit_errors
    return bit_errors

def ber_test_thread(port_name, baud_rate, prbs_type, chunk_size, stop_event, pause_event, update_callback, status_callback):
    """Arka planda BER testini yürüten iş parçacığı fonksiyonu."""
    global TOTAL_BITS_SENT, TOTAL_BITS_RECEIVED, TOTAL_BITS_ERROR
    
    TOTAL_BITS_SENT, TOTAL_BITS_RECEIVED, TOTAL_BITS_ERROR = 0, 0, 0
    
    prbs_gen = None
    if prbs_type != "HİÇBİRİ":
        try:
            prbs_gen = PRBS_Generator(int(prbs_type))
        except ValueError as e:
            status_callback(f"HATA: PRBS başlatılamadı - {e}", error=True)
            return

    ser = None
    try:
        ser = serial.Serial(port_name, baud_rate, timeout=0.1)
        ser.flushInput() 
        ser.flushOutput()
    except serial.SerialException as e:
        status_callback(f"HATA: Seri Port Açılamadı - {e}", error=True)
        return
        
    try:
        while not stop_event.is_set():
            
            if pause_event.is_set():
                status_callback("Test Duraklatıldı...", special=True)
                time.sleep(0.1)
                continue
            
            if prbs_gen:
                chunk = generate_prbs_data(chunk_size, prbs_gen)
            else:
                chunk = generate_random_data(chunk_size)

            try:
                ser.write(chunk)
                TOTAL_BITS_SENT += len(chunk) * 8
            except serial.SerialException:
                status_callback("Gönderim Hatası!", error=True)
                break

            received = b''
            read_start = time.time()
            timeout = len(chunk) * 8 / baud_rate + 0.5 
            
            while len(received) < len(chunk) and (time.time() - read_start) < timeout and not stop_event.is_set():
                if ser.in_waiting > 0:
                    received += ser.read(ser.in_waiting)
                time.sleep(0.001)

            if stop_event.is_set():
                if len(received) != len(chunk):
                    TOTAL_BITS_SENT -= len(chunk) * 8
                    
                if ser and ser.is_open:
                    ser.flushInput()
                    
                break

            TOTAL_BITS_RECEIVED += len(received) * 8

            calculate_bit_errors(chunk, received)

            update_callback(TOTAL_BITS_SENT, TOTAL_BITS_RECEIVED, TOTAL_BITS_ERROR)
            
            time.sleep(0.05)

    except serial.SerialException as e:
        status_callback(f"Seri İletişim Hatası: {e}", error=True)
    except Exception as e:
        status_callback(f"Test Sırasında Beklenmeyen Hata: {e}", error=True)
    finally:
        if ser and ser.is_open:
            ser.close()
            status_callback("Test sonlandı. Port kapatıldı.")
        if not stop_event.is_set():
            stop_event.set()

# --- GUI ---
class BERTesterApp:
    def __init__(self, root):
        self.root = root
        root.title("Ber Test")
        
        self.stop_event = threading.Event()
        self.pause_event = threading.Event() 
        self.thread = None
        self.is_test_running = False
        self.is_paused = False

        self.test_start_time = 0.0
        self.pause_start_time = 0.0
        self.total_paused_time = 0.0
        self.chronometer_id = None 

        self._setup_gui_elements()
        self.update_status("Başlatılmaya hazır.")
        
        root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
    def _setup_gui_elements(self):
        """Ana GUI elemanlarını ayarlar."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        row_idx = 0
        
        tk.Label(main_frame, text="COM Port:").grid(row=row_idx, column=0, sticky='w', pady=2)
        self.com_combo = ttk.Combobox(main_frame, values=self.list_com_ports(), width=15)
        self.com_combo.grid(row=row_idx, column=1, sticky='we', pady=2)
        if self.list_com_ports(): self.com_combo.current(0)
        row_idx += 1

        tk.Label(main_frame, text="Baud Rate:").grid(row=row_idx, column=0, sticky='w', pady=2)
        baud_rates = ["200", "300", "600", "1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"]
        self.baud_combo = ttk.Combobox(main_frame, values=baud_rates, width=15)
        self.baud_combo.set("200") 
        self.baud_combo.grid(row=row_idx, column=1, sticky='we', pady=2)
        row_idx += 1

        tk.Label(main_frame, text="PRBS Tipi:").grid(row=row_idx, column=0, sticky='w', pady=2)
        self.prbs_combo = ttk.Combobox(main_frame, values=["7","15","23","HİÇBİRİ"], width=15, state='readonly')
        self.prbs_combo.current(3)
        self.prbs_combo.grid(row=row_idx, column=1, sticky='we', pady=2)
        row_idx += 1

        tk.Label(main_frame, text="Chunk Boyutu (bytes):").grid(row=row_idx, column=0, sticky='w', pady=2)
        self.chunk_entry = tk.Entry(main_frame, width=17)
        self.chunk_entry.insert(0, "1")
        self.chunk_entry.grid(row=row_idx, column=1, sticky='we', pady=2)
        row_idx += 1

        tk.Label(main_frame, text="Süre (s, 0=Sürekli):").grid(row=row_idx, column=0, sticky='w', pady=2)
        self.duration_entry = tk.Entry(main_frame, width=17)
        self.duration_entry.insert(0, "0")
        self.duration_entry.grid(row=row_idx, column=1, sticky='we', pady=2)
        row_idx += 1
        
        ttk.Separator(main_frame, orient='horizontal').grid(row=row_idx, column=0, columnspan=2, sticky="ew", pady=5)
        row_idx += 1
        
        # --- Butonlar ---
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row_idx, column=0, columnspan=2, pady=10)
        
        self.start_btn = tk.Button(button_frame, text="▶ Başlat", command=self.start_test, bg='green', fg='white', width=10)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.pause_btn = tk.Button(button_frame, text="⏸ Duraklat", command=self.toggle_pause, bg='orange', fg='black', width=10, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(button_frame, text="◼ Durdur", command=self.stop_test, bg='red', fg='white', width=10, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        row_idx += 1
        
        ttk.Separator(main_frame, orient='horizontal').grid(row=row_idx, column=0, columnspan=2, sticky="ew", pady=5)
        row_idx += 1
        
        self.status_label = tk.Label(main_frame, text="Durum: Hazır.", anchor='w', relief=tk.SUNKEN, bd=1)
        self.status_label.grid(row=row_idx, column=0, columnspan=2, sticky='we', pady=2)
        row_idx += 1
        
        self.duration_label = tk.Label(main_frame, text="Toplam Süre: 0.00 s", anchor='w')
        self.duration_label.grid(row=row_idx, column=0, sticky='w', pady=1)
        self.sent_label = tk.Label(main_frame, text="Gönderilen Bit: 0", anchor='e')
        self.sent_label.grid(row=row_idx, column=1, sticky='e', pady=1)
        row_idx += 1
        
        self.received_label = tk.Label(main_frame, text="Gelen Bit: 0", anchor='w')
        self.received_label.grid(row=row_idx, column=0, sticky='w', pady=1)
        self.error_label = tk.Label(main_frame, text="Toplam Hata: 0", fg='red', anchor='e')
        self.error_label.grid(row=row_idx, column=1, sticky='e', pady=1)
        row_idx += 1

    def list_com_ports(self):
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports] or ["COM1 (Hata)"]
    
    def update_status(self, message, error=False, special=False):
        if special: color = 'blue'
        elif error: color = 'red'
        else: color = 'black'
        self.status_label.config(text=f"Durum: {message}", fg=color)
        self.root.update_idletasks()
        
    def update_callback(self, sent, received, errors):
        """Test iş parçacığından gelen verilerle GUI'yi günceller."""
        
        self.sent_label.config(text=f"Gönderilen Bit: {sent:,}")
        self.received_label.config(text=f"Gelen Bit: {received:,}") 
        self.error_label.config(text=f"Toplam Hata: {errors:,}")
        
        if not self.is_paused:
             self.update_status(f"Test Çalışıyor...")
             
    def update_chronometer(self):
        """Ana döngüde bağımsız olarak süreyi günceller ve süre kontrolünü yapar."""
        if not self.is_test_running:
            return

        current_time = time.time()
        
        if self.is_paused:
            if self.pause_start_time == 0.0:
                 self.pause_start_time = current_time
                 
            frozen_elapsed_time = (self.pause_start_time - self.test_start_time) - self.total_paused_time
            self.duration_label.config(text=f"Toplam Süre: {frozen_elapsed_time:.2f} s (DURAKLATILDI)")
            
        else: 
            
            if self.pause_start_time != 0.0:
                self.total_paused_time += (current_time - self.pause_start_time)
                self.pause_start_time = 0.0
                
            elapsed_time = (current_time - self.test_start_time) - self.total_paused_time
            self.duration_label.config(text=f"Toplam Süre: {elapsed_time:.2f} s")
            
            try:
                duration_limit = int(self.duration_entry.get())
                if duration_limit > 0 and elapsed_time >= duration_limit:
                    self.update_status("Test süresi doldu. Otomatik durduruluyor.")
                    self.stop_test()
                    return 
            except ValueError:
                 pass

        self.chronometer_id = self.root.after(100, self.update_chronometer)


    def start_test(self):
        """Testi başlatır."""
        if self.is_test_running:
            messagebox.showwarning("Uyarı", "Test zaten çalışıyor.")
            return

        com_port = self.com_combo.get()
        prbs_type = self.prbs_combo.get()
        
        try:
            baud = int(self.baud_combo.get()) 
            chunk_size = int(self.chunk_entry.get())
            duration = int(self.duration_entry.get()) 
            if baud <= 0 or chunk_size <= 0 or duration < 0:
                 raise ValueError("Baud, Chunk Size pozitif, Süre pozitif veya 0 olmalıdır.")
        except ValueError as e:
            messagebox.showerror("Hata", f"Geçersiz giriş: {e}")
            return
        
        global TOTAL_BITS_SENT, TOTAL_BITS_RECEIVED, TOTAL_BITS_ERROR
        TOTAL_BITS_SENT, TOTAL_BITS_RECEIVED, TOTAL_BITS_ERROR = 0, 0, 0
        
        self.test_start_time = time.time()
        self.total_paused_time = 0.0
        self.pause_start_time = 0.0
        
        self.duration_label.config(text="Toplam Süre: 0.00 s")
        self.sent_label.config(text="Gönderilen Bit: 0")
        self.received_label.config(text="Gelen Bit: 0")
        self.error_label.config(text="Toplam Hata: 0")
        
        self.stop_event.clear()
        self.pause_event.clear()
        
        self.thread = threading.Thread(target=ber_test_thread,
                                         args=(com_port, baud, prbs_type, chunk_size, 
                                               self.stop_event, self.pause_event, self.update_callback, self.update_status))
        self.thread.daemon = True
        self.thread.start()
        
        self.is_test_running = True
        self.is_paused = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.NORMAL, text="⏸ Duraklat", bg='orange', fg='black')
        self.update_status(f"Test Başlatıldı: {com_port} @ {baud} bps")

        self.update_chronometer()

    def toggle_pause(self):
        """Testi duraklatır veya devam ettirir."""
        if not self.is_test_running:
            return
            
        if not self.is_paused:
            self.pause_event.set() 
            self.is_paused = True
            self.pause_btn.config(text="▶ Devam Et", bg='blue', fg='white')
        else:
            self.pause_event.clear() 
            self.is_paused = False
            self.pause_btn.config(text="⏸ Duraklat", bg='orange', fg='black')
            self.update_status("Test Devam Ediyor...")
            

    def stop_test(self):
        """Testi durdurur."""
        if not self.is_test_running:
            messagebox.showwarning("Uyarı", "Çalışan bir test yok.")
            return
            
        self.update_status("Test durduruluyor, lütfen bekleyin...")
        
        if self.chronometer_id:
             self.root.after_cancel(self.chronometer_id)
             self.chronometer_id = None
        
        if self.is_paused:
            self.pause_event.clear()
            self.is_paused = False
        
        self.stop_event.set()
        
        if self.thread and self.thread.is_alive():
             self.thread.join(timeout=2)
        
        self.is_test_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.DISABLED, text="⏸ Duraklat")
        
        elapsed_time = (time.time() - self.test_start_time) - self.total_paused_time
        self.duration_label.config(text=f"Toplam Süre: {elapsed_time:.2f} s (SON)")
        self.update_status("Test Durduruldu. Sonuçlar ekranda.")

    def _on_closing(self):
        """Uygulama kapatılırken iş parçacığını durdurur."""
        if self.thread and self.thread.is_alive():
            if messagebox.askyesno("Çıkış Onayı", "Çalışan bir test var. Durdurulup çıkılsın mı?"):
                if self.chronometer_id:
                     self.root.after_cancel(self.chronometer_id)
                self.stop_event.set()
                self.thread.join(timeout=2)
                self.root.destroy()
            else:
                return
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = BERTesterApp(root)
    root.mainloop()