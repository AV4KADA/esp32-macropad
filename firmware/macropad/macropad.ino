/*
 * ESP32-C3 MacroPad - Firmware v7.0 (Ultimate Edition)
 * Исправлено: Статичный LED в конфиге (для настройки яркости),
 * профили и хотплаг (поддержка со стороны ПК).
 */

#include <Arduino.h>
#include <BleKeyboard.h>
#include <Preferences.h>
#include <ArduinoJson.h>

// ================== ПИНЫ (МАТРИЦА 3x2) ==================
// [1][2][3] -> GPIO 3, 5, 0
// [4][5][6] -> GPIO 4, 7, 10
const int MACRO_BUTTONS[] = {3, 5, 0, 4, 7, 10}; 
#define BUTTON_COUNT 6

const int WAKEUP_BUTTON_PIN = 1; 
const int STATUS_LED_PIN = 6;    

// ================== СПЕЦ. КОДЫ (MEDIA) ==================
#define KEY_MEDIA_PLAY_PAUSE_CUSTOM 205
#define KEY_MEDIA_VOL_UP_CUSTOM     206
#define KEY_MEDIA_VOL_DOWN_CUSTOM   207
#define KEY_MEDIA_MUTE_CUSTOM       208
#define KEY_MEDIA_NEXT_TRACK        209
#define KEY_MEDIA_PREV_TRACK        210

// ================== СТРУКТУРЫ ==================
#define MAX_ACTIONS 30 

enum ActionType : uint8_t { 
  ACT_PRESS = 1, 
  ACT_RELEASE = 2, 
  ACT_DELAY = 3 
};

struct MacroAction {
  uint8_t type;
  uint8_t key;
  uint16_t value; 
};

struct Macro {
  uint8_t mode; // 0=Macro, 1=Hold
  uint8_t length;
  MacroAction actions[MAX_ACTIONS];
};

struct DeviceConfig {
  uint32_t sleep_timeout_ms;
  uint8_t led_brightness;
  Macro macros[BUTTON_COUNT];
  uint8_t magic_byte;
};

// ================== ОБЪЕКТЫ ==================
BleKeyboard bleKeyboard("ESP32 MacroPad", "Pro V7", 100);
Preferences prefs;
DeviceConfig config;

bool buttonStates[BUTTON_COUNT] = {false};
bool isConfigMode = false;
unsigned long lastActivityTime = 0;

enum LedState { LED_OFF, LED_CONFIG, LED_SEARCHING, LED_CONNECTED, LED_ACTION, LED_SLEEPING };
LedState currentLedState = LED_SEARCHING;
unsigned long ledTimer = 0;
int ledValue = 0;
bool ledDir = true;

// ================== ПРОТОТИПЫ ==================
void loadConfig();
void saveConfig();
void loadDefaultConfig();
void sendConfigToPC();
void goToDeepSleep();
void setLedState(LedState state);
void updateStatusLED();
void handleButtonPress(uint8_t index);
void handleButtonRelease(uint8_t index);
void checkPowerButton();
void pressKeySafe(uint8_t key);
void releaseKeySafe(uint8_t key);

// ================== SETUP ==================
void setup() {
  Serial.begin(115200);
  
  pinMode(STATUS_LED_PIN, OUTPUT);
  pinMode(WAKEUP_BUTTON_PIN, INPUT);
  
  for (int i = 0; i < BUTTON_COUNT; i++) {
    pinMode(MACRO_BUTTONS[i], INPUT_PULLUP);
  }

  loadConfig();
  
  // Тест LED при старте
  analogWrite(STATUS_LED_PIN, config.led_brightness);
  delay(300);
  analogWrite(STATUS_LED_PIN, 0);

  // === SAFE BOOT (Вход в конфиг) ===
  // Если нажата Кнопка 1 при включении -> принудительный конфиг
  if (digitalRead(MACRO_BUTTONS[0]) == LOW) {
    isConfigMode = true;
    setLedState(LED_CONFIG);
    Serial.println("READY_FOR_CONFIG");
    while(digitalRead(MACRO_BUTTONS[0]) == LOW) delay(10);
  } 
  else {
    isConfigMode = false;
    bleKeyboard.begin();
    setLedState(LED_SEARCHING);
    lastActivityTime = millis();
    Serial.println("MODE: KEYBOARD");
  }
}

// ================== LOOP ==================
void loop() {
  updateStatusLED();
  checkPowerButton();

  // --- РЕЖИМ КОНФИГУРАТОРА ---
  if (isConfigMode) {
    if (Serial.available()) {
      String input = Serial.readStringUntil('\n');
      if (input.length() > 0) {
        lastActivityTime = millis();
        
        StaticJsonDocument<4096> doc;
        DeserializationError error = deserializeJson(doc, input);

        if (!error) {
          const char* cmd = doc["cmd"];
          
          if (strcmp(cmd, "ping") == 0) {
            Serial.println("{\"status\":\"ok\",\"cmd\":\"ping\"}");
          }
          else if (strcmp(cmd, "get_config") == 0) {
             sendConfigToPC(); 
          }
          else if (strcmp(cmd, "set_settings") == 0) {
            if (doc.containsKey("brightness")) {
               config.led_brightness = doc["brightness"];
               // Сразу применяем яркость, чтобы пользователь видел результат
               if(currentLedState == LED_CONFIG) analogWrite(STATUS_LED_PIN, config.led_brightness);
            }
            if (doc.containsKey("sleep")) config.sleep_timeout_ms = doc["sleep"];
            Serial.println("{\"status\":\"ok\"}");
          }
          else if (strcmp(cmd, "set_macro") == 0) {
            int btn = doc["button"];
            if (btn >= 0 && btn < BUTTON_COUNT) {
              config.macros[btn].length = 0;
              config.macros[btn].mode = doc["mode"];
              
              JsonArray acts = doc["actions"];
              for (JsonObject a : acts) {
                if (config.macros[btn].length >= MAX_ACTIONS) break;
                MacroAction &ma = config.macros[btn].actions[config.macros[btn].length++];
                
                const char *t = a["t"];
                ma.key = a["k"];
                ma.value = a["v"];
                
                if (strcmp(t, "press") == 0) ma.type = ACT_PRESS;
                else if (strcmp(t, "release") == 0) ma.type = ACT_RELEASE;
                else if (strcmp(t, "delay") == 0) ma.type = ACT_DELAY;
              }
              Serial.print("{\"status\":\"ok\",\"btn\":"); Serial.print(btn); Serial.println("}");
            }
          }
          else if (strcmp(cmd, "save") == 0) {
            config.magic_byte = 0x42;
            saveConfig();
            Serial.println("{\"status\":\"saved\"}");
            delay(500);
            ESP.restart();
          }
          else if (strcmp(cmd, "reset") == 0) {
            loadDefaultConfig();
            saveConfig();
            Serial.println("{\"status\":\"reset\"}");
            delay(500);
            ESP.restart();
          }
        }
      }
    }
    return;
  }

  // --- РЕЖИМ КЛАВИАТУРЫ ---
  if (bleKeyboard.isConnected() && currentLedState == LED_SEARCHING) {
    setLedState(LED_CONNECTED);
  } else if (!bleKeyboard.isConnected() && currentLedState == LED_CONNECTED) {
    setLedState(LED_SEARCHING);
  }

  // Сон
  if (config.sleep_timeout_ms > 0 && millis() - lastActivityTime > config.sleep_timeout_ms) {
    goToDeepSleep();
  }

  if (bleKeyboard.isConnected()) {
    for (int i = 0; i < BUTTON_COUNT; i++) {
      bool pressed = (digitalRead(MACRO_BUTTONS[i]) == LOW);
      
      if (pressed && !buttonStates[i]) {
        delay(20); 
        if (digitalRead(MACRO_BUTTONS[i]) == LOW) {
          buttonStates[i] = true;
          lastActivityTime = millis();
          setLedState(LED_ACTION);
          handleButtonPress(i);
        }
      }
      else if (!pressed && buttonStates[i]) {
        buttonStates[i] = false;
        lastActivityTime = millis();
        handleButtonRelease(i);
      }
    }
  }
  delay(5);
}

// ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================

void sendConfigToPC() {
    Serial.print("{\"cmd\":\"config_data\",\"bri\":");
    Serial.print(config.led_brightness);
    Serial.print(",\"sleep\":");
    Serial.print(config.sleep_timeout_ms);
    Serial.println("}");
    delay(50); 

    for(int i=0; i<BUTTON_COUNT; i++) {
        Serial.print("{\"cmd\":\"macro_data\",\"btn\":");
        Serial.print(i);
        Serial.print(",\"mode\":");
        Serial.print(config.macros[i].mode);
        Serial.print(",\"actions\":[");
        
        for(int j=0; j<config.macros[i].length; j++) {
            MacroAction &ma = config.macros[i].actions[j];
            Serial.print("{\"t\":\"");
            if(ma.type == ACT_PRESS) Serial.print("press");
            else if(ma.type == ACT_RELEASE) Serial.print("release");
            else Serial.print("delay");
            Serial.print("\",\"k\":");
            Serial.print(ma.key);
            Serial.print(",\"v\":");
            Serial.print(ma.value);
            Serial.print("}");
            if(j < config.macros[i].length - 1) Serial.print(",");
        }
        Serial.println("]}");
        delay(30); 
    }
    Serial.println("{\"cmd\":\"config_end\"}");
}

void pressKeySafe(uint8_t key) {
  if (key >= 200) {
    switch(key) {
      case KEY_MEDIA_VOL_UP_CUSTOM: bleKeyboard.write(KEY_MEDIA_VOLUME_UP); break;
      case KEY_MEDIA_VOL_DOWN_CUSTOM: bleKeyboard.write(KEY_MEDIA_VOLUME_DOWN); break;
      case KEY_MEDIA_MUTE_CUSTOM: bleKeyboard.write(KEY_MEDIA_MUTE); break;
      case KEY_MEDIA_PLAY_PAUSE_CUSTOM: bleKeyboard.write(KEY_MEDIA_PLAY_PAUSE); break;
      case KEY_MEDIA_NEXT_TRACK: bleKeyboard.write(KEY_MEDIA_NEXT_TRACK); break;
      case KEY_MEDIA_PREV_TRACK: bleKeyboard.write(KEY_MEDIA_PREVIOUS_TRACK); break;
    }
  } else {
    bleKeyboard.press(key);
  }
}

void releaseKeySafe(uint8_t key) {
  if (key < 200) {
    bleKeyboard.release(key);
  }
}

void handleButtonPress(uint8_t index) {
  Macro &m = config.macros[index];
  if (m.length == 0) return;

  if (m.mode == 1) { // HOLD
    for (int i = 0; i < m.length; i++) {
      if (m.actions[i].type == ACT_PRESS) pressKeySafe(m.actions[i].key);
    }
  } else { // SEQUENCE
    for (int i = 0; i < m.length; i++) {
      switch (m.actions[i].type) {
        case ACT_PRESS: pressKeySafe(m.actions[i].key); break;
        case ACT_RELEASE: releaseKeySafe(m.actions[i].key); break;
        case ACT_DELAY: delay(m.actions[i].value); break;
      }
    }
    bleKeyboard.releaseAll();
  }
}

void handleButtonRelease(uint8_t index) {
  Macro &m = config.macros[index];
  if (m.mode == 1) { 
    for (int i = 0; i < m.length; i++) {
      if (m.actions[i].type == ACT_PRESS) releaseKeySafe(m.actions[i].key);
    }
    bleKeyboard.releaseAll();
  }
}

void checkPowerButton() {
  if (digitalRead(WAKEUP_BUTTON_PIN) == LOW) {
    delay(30);
    if (digitalRead(WAKEUP_BUTTON_PIN) == LOW) {
      lastActivityTime = millis();
      unsigned long holdStart = millis();
      
      while(digitalRead(WAKEUP_BUTTON_PIN) == LOW) {
        if (millis() - holdStart > 2000) {
           setLedState(LED_SLEEPING);
           for(int i=config.led_brightness; i>=0; i-=5) {
             analogWrite(STATUS_LED_PIN, i); delay(10);
           }
           while(digitalRead(WAKEUP_BUTTON_PIN) == LOW) delay(10); 
           goToDeepSleep();
        }
        delay(10);
      }
    }
  }
}

void goToDeepSleep() {
  setLedState(LED_OFF);
  bleKeyboard.end();
  esp_deep_sleep_enable_gpio_wakeup(1ULL << WAKEUP_BUTTON_PIN, ESP_GPIO_WAKEUP_GPIO_LOW);
  uint64_t mask = (1ULL << WAKEUP_BUTTON_PIN);
  for(int i=0; i<BUTTON_COUNT; i++) mask |= (1ULL << MACRO_BUTTONS[i]);
  esp_deep_sleep_enable_gpio_wakeup(mask, ESP_GPIO_WAKEUP_GPIO_LOW);
  esp_deep_sleep_start();
}

void setLedState(LedState state) {
  currentLedState = state;
  ledTimer = millis();
  ledValue = 0;
}

void updateStatusLED() {
  unsigned long now = millis();
  switch (currentLedState) {
    case LED_CONFIG: 
      // СТАТИЧНЫЙ СВЕТ для точной настройки яркости
      analogWrite(STATUS_LED_PIN, config.led_brightness);
      break;
    case LED_SEARCHING:
      if (now - ledTimer > 15) {
        ledTimer = now;
        if (ledDir) { ledValue += 5; if (ledValue >= config.led_brightness) ledDir = false; }
        else { ledValue -= 5; if (ledValue <= 0) ledDir = true; }
        analogWrite(STATUS_LED_PIN, constrain(ledValue, 0, 255));
      }
      break;
    case LED_CONNECTED:
      if (now - ledTimer > 5000) {
        analogWrite(STATUS_LED_PIN, config.led_brightness);
        delay(50); analogWrite(STATUS_LED_PIN, 0); ledTimer = now;
      } else analogWrite(STATUS_LED_PIN, 0);
      break;
    case LED_ACTION:
      analogWrite(STATUS_LED_PIN, config.led_brightness);
      if (now - ledTimer > 150) setLedState(bleKeyboard.isConnected() ? LED_CONNECTED : LED_SEARCHING);
      break;
    case LED_OFF: case LED_SLEEPING: analogWrite(STATUS_LED_PIN, 0); break;
  }
}

void loadConfig() {
  prefs.begin("macropad", true);
  if (prefs.getBytesLength("cfg") == sizeof(DeviceConfig)) {
    prefs.getBytes("cfg", &config, sizeof(DeviceConfig));
    if (config.magic_byte != 0x42) loadDefaultConfig();
  } else {
    loadDefaultConfig();
  }
  prefs.end();
}

void saveConfig() {
  prefs.begin("macropad", false);
  prefs.putBytes("cfg", &config, sizeof(DeviceConfig));
  prefs.end();
}

void loadDefaultConfig() {
  config.sleep_timeout_ms = 300000;
  config.led_brightness = 150;
  config.magic_byte = 0x42;
  for (int i=0; i<BUTTON_COUNT; i++) {
    config.macros[i].length = 0;
    config.macros[i].mode = 0;
  }
}