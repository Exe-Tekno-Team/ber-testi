BER Tester

Python ile geliştirilmiş, seri port üzerinden Bit Error Rate (BER) testi yapabilen bir uygulamadır. PRBS ve rastgele veri gönderimi ile iletişim hatalarını ölçebilir ve gerçek zamanlı istatistikleri görebilirsiniz.

Özellikler

PRBS-7, PRBS-15 ve PRBS-23 desteği

Rastgele veri gönderimi

Gönderilen/gelen bit sayısı ve toplam hata sayısı takibi

Testi başlatma, duraklatma ve durdurma

Otomatik süre sınırı ile test durdurma

Gereksinimler

Python 3.7 veya üstü

Gerekli kütüphaneler:

pip install pyserial

Kurulum

Depoyu klonlayın:

git clone https://github.com/Exe-Tekno-Team/ber-testi.git


Çalıştırmak için:

python ber_tester.py

Kullanım

Programı başlatın:

python ber_tester.py


Seri portu seçin (örn: COM1, COM3, /dev/ttyUSB0)

Baud rate seçin (örn: 200, 9600, 115200)

PRBS tipi seçin veya "HİÇBİRİ" seçerek rastgele veri kullanın

Chunk boyutunu ve test süresini girin (0 = süresiz)

Başlat butonuna basın

Test sırasında:

Duraklat: Testi duraklatır veya devam ettirir

Durdur: Testi sonlandırır

Test bittikten sonra, gönderilen/gelen bit ve toplam hata sayısı ekranda görüntülenir

Örnek Ekran Görüntüsü

(Opsiyonel: burada GUI ekran görüntüsü paylaşabilirsin)

Lisans

MIT Lisansı - istediğiniz gibi kullanabilirsiniz.
