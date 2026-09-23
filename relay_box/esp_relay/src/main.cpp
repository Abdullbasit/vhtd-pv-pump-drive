/* HS300 attack relay box - YD-ESP32-C3-4IN4OUT (vcc-gnd), 2026-09-08.
 *
 * Four relays that throw the disturbance loads for the PV-direct pump drive
 * tests: resistor banks and the string isolator, 40 m from the laptop, so
 * they are commanded over WiFi/MQTT with the same AP list and the same
 * public broker as the converter agent (dc_dc_g474_batt_mppt/esp32), and
 * over the USB serial as the fallback.
 *
 * From the schematic: K1..K4 (SRD-5V) on GPIO4..GPIO7 through NPN drivers,
 * active HIGH; KEY1..KEY4 on GPIO0/1/8/9, active LOW; CH340 on UART0.
 *
 * TWO PATHS, like the converter agent: LOCAL - an HTTP server on the LAN,
 * http://hs300relay.local/cmd?c=R1%20ON%2090 (mDNS) or by IP, answered in
 * the response body, no internet needed; CLOUD - MQTT through the public
 * broker for when the laptop is on a different network. Serial is the
 * third, over the USB cable.
 *
 * CHANNELS, as wired 2026-09-08 (CH_NAME below): R1 LOAD - the resistor
 * bank, size preset by its breakers; R2 STRING - the string isolator on the
 * relay's NC contact, so energised = string OUT, released = string IN;
 * R3, R4 SPARE.
 *
 * COMMANDS - one line, same grammar on serial, HTTP and relay/<ID>/cmd:
 *   R<n> ON [secs]   close relay n (1..4); with secs it opens by itself
 *   R<n> OFF         open relay n
 *   LOAD ON [secs] | LOAD OFF        same as R1
 *   STRING OUT | STRING IN           same as R2 ON | R2 OFF
 *   ALL OFF          open every relay
 *   STATUS           publish/print the state
 * REPLIES: "OK R1=0 R2=1 R3=0 R4=0 up=123" after every command, and an
 * unsolicited "EV R2=1 t=123456" (ms since boot) on every contact change,
 * on serial and on relay/<ID>/ev, so the PC log has the instant it moved.
 *
 * OTA: ArduinoOTA on the LAN (hostname MDNS_NAME, password ESP_OTA_PASSWORD)
 * - `pio run -e yd_esp32c3_ota -t upload` from tools/esp_relay. Every relay
 * is opened the moment an update starts, so a flash mid-test cannot leave a
 * load or the string isolator hanging.
 *
 * SAFETY: every relay opens at boot; a relay with a timer opens when the
 * timer runs out whether or not anyone is listening; the broker's last
 * will marks relay/<ID>/status "offline" if the box drops off. The front
 * keys toggle their relay by hand (with the same EV line) so the array box
 * can still be worked without the laptop. */
#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <ArduinoOTA.h>
#include "ui.h"                 /* the phone page, GET /ui */

/* ---- WiFi: the converter agent's list, strongest present AP wins ------ */
struct WifiAp { const char *ssid; const char *pass; };
static const WifiAp WIFI_APS[] = {
  { "SSID_1",       "PASSWORD_1" },
  { "SSID_2",       "PASSWORD_2" },   /* Starlink router */
  { "SSID_3",       "PASSWORD_3" },   /* phone hotspot   */
};
static const int N_WIFI_APS = sizeof(WIFI_APS) / sizeof(WIFI_APS[0]);

/* ---- MQTT: public HiveMQ like the converter; the id is the only secret - */
#define MQTT_HOST   "broker.hivemq.com"
#define MQTT_PORT   1883
#define DEVICE_ID   "hs300relay-q7v2mk"     /* topics relay/<DEVICE_ID>/... */
#define MDNS_NAME   "hs300relay"            /* http://hs300relay.local/      */
#define ESP_OTA_PASSWORD "SET_YOUR_OWN"  /* ArduinoOTA on the LAN          */

static const uint8_t RELAY_PIN[4] = {4, 5, 6, 7};
static const char   *CH_NAME[4]   = {"LOAD", "STRING", "SPARE3", "SPARE4"};
static const uint8_t KEY_PIN[4]   = {0, 1, 8, 9};
static bool     st[4]       = {0, 0, 0, 0};
static uint32_t off_at[4]   = {0, 0, 0, 0};   /* millis() deadline, 0 = none */
static uint8_t  key_last[4] = {1, 1, 1, 1};
static uint32_t key_ms[4]   = {0, 0, 0, 0};

static WiFiClient   net;
static PubSubClient mqtt(net);
static WebServer    httpd(80);
static String       last_reply;            /* what the HTTP path answers with */
static bool         mdns_up = false;
static bool         ota_up  = false;
static uint32_t     wifi_next = 0, mqtt_next = 0;
static IPAddress    mqtt_ip;                 /* broker resolved once per link */
static uint32_t     loop_last = 0, stall_max = 0;   /* longest gap between loop passes, ms */

static String T(const char *leaf) { return String("relay/" DEVICE_ID "/") + leaf; }

static void out(const char *leaf, const String &s) {
  Serial.println(s);
  if (!strcmp(leaf, "reply")) last_reply = s;
  if (mqtt.connected()) mqtt.publish(T(leaf).c_str(), s.c_str(), false);
}
static String statusLine() {
  char b[112];
  snprintf(b, sizeof b, "OK R1=%d R2=%d R3=%d R4=%d up=%lu LOAD=%s STRING=%s stall=%lu mqtt=%d rssi=%d", st[0], st[1], st[2], st[3],
           (unsigned long)(millis() / 1000), st[0] ? "ON" : "OFF", st[1] ? "OUT" : "IN",
           (unsigned long)stall_max, mqtt.connected() ? 1 : 0, (int)WiFi.RSSI());
  stall_max = 0;
  return String(b);
}
static void announce(int i) {
  char b[56];
  snprintf(b, sizeof b, "EV R%d=%d %s t=%lu", i + 1, st[i] ? 1 : 0, CH_NAME[i], (unsigned long)millis());
  out("ev", String(b));
}
static void set_relay(int i, bool on, uint32_t secs) {
  st[i] = on;
  digitalWrite(RELAY_PIN[i], on ? HIGH : LOW);
  off_at[i] = (on && secs) ? millis() + secs * 1000UL : 0;
  announce(i);
}
static void status() {
  String s = statusLine();
  out("reply", s);
  if (mqtt.connected()) mqtt.publish(T("status").c_str(), s.c_str(), true);
}

static void handle(char *s) {
  char buf[48];
  for (char *p = s; *p; p++) *p = toupper((unsigned char)*p);
  if (!strncmp(s, "STATUS", 6)) { status(); return; }
  /* named channels map onto the R<n> grammar below */
  if (!strncmp(s, "LOAD", 4))   { snprintf(buf, sizeof buf, "R1%s", s + 4); s = buf; }
  else if (!strncmp(s, "STRING OUT", 10)) { s = (char *)"R2 ON"; }
  else if (!strncmp(s, "STRING IN", 9))   { s = (char *)"R2 OFF"; }
  if (!strncmp(s, "ALL OFF", 7)) { for (int i = 0; i < 4; i++) set_relay(i, false, 0); status(); return; }
  if (s[0] == 'R' && s[1] >= '1' && s[1] <= '4') {
    int i = s[1] - '1';
    const char *a = s + 2; while (*a == ' ') a++;
    if (!strncmp(a, "ON", 2)) {
      uint32_t secs = 0; const char *b = a + 2; while (*b == ' ') b++;
      if (*b) secs = strtoul(b, NULL, 10);
      set_relay(i, true, secs); status(); return;
    }
    if (!strncmp(a, "OFF", 3)) { set_relay(i, false, 0); status(); return; }
  }
  out("reply", String("ERR ") + s);
}

/* ---- WiFi: scan, join the strongest listed AP, never block the relays -- */
static void wifiTry() {
  if (WiFi.status() == WL_CONNECTED) return;
  int n = WiFi.scanNetworks();
  int best = -1, bestRssi = -999;
  for (int k = 0; k < n; k++)
    for (int a = 0; a < N_WIFI_APS; a++)
      if (WiFi.SSID(k) == WIFI_APS[a].ssid && WiFi.RSSI(k) > bestRssi) { best = a; bestRssi = WiFi.RSSI(k); }
  WiFi.scanDelete();
  if (best < 0) { Serial.println("wifi: none of the listed APs in range"); return; }
  Serial.printf("wifi: joining %s (%d dBm)\n", WIFI_APS[best].ssid, bestRssi);
  WiFi.begin(WIFI_APS[best].ssid, WIFI_APS[best].pass);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 8000) delay(100);
  if (WiFi.status() == WL_CONNECTED) Serial.printf("wifi: %s\n", WiFi.localIP().toString().c_str());
}

/* ---- LOCAL path: GET /cmd?c=<command>  GET /status  GET / ------------- */
static void httpCmd() {
  String c = httpd.arg("c");
  char line[48];
  c.toCharArray(line, sizeof line);
  last_reply = "";
  if (c.length()) handle(line); else status();
  httpd.send(200, "text/plain", last_reply + "\n");
}
static void httpStatus() { httpd.send(200, "text/plain", statusLine() + "\n"); }
static void httpRoot() {
  httpd.send(200, "text/plain",
    String("HS300 relay box " DEVICE_ID "\n"
           "  R1 LOAD   R2 STRING (NC: ON = out)   R3/R4 spare\n"
           "  GET /cmd?c=LOAD%20ON%2090   GET /cmd?c=STRING%20OUT   GET /cmd?c=ALL%20OFF   GET /status\n")
    + statusLine() + "\n");
}
static void localTry() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (!mdns_up && MDNS.begin(MDNS_NAME)) { MDNS.addService("http", "tcp", 80); mdns_up = true;
    Serial.println("mdns: http://" MDNS_NAME ".local/"); }
  if (!ota_up) {
    ArduinoOTA.setHostname(MDNS_NAME);
    ArduinoOTA.setPassword(ESP_OTA_PASSWORD);
    ArduinoOTA.onStart([]() {
      for (int i = 0; i < 4; i++) set_relay(i, false, 0);   /* nothing hangs on */
      Serial.println("ota: start, all relays opened");
    });
    ArduinoOTA.onEnd([]()  { Serial.println("ota: done, rebooting"); });
    ArduinoOTA.onError([](ota_error_t e) { Serial.printf("ota: error %u\n", (unsigned)e); });
    ArduinoOTA.begin();
    ota_up = true;
    Serial.println("ota: ready");
  }
}

static void mqttCallback(char *topic, byte *payload, unsigned int len) {
  char line[48];
  if (len >= sizeof line) len = sizeof line - 1;
  memcpy(line, payload, len); line[len] = 0;
  Serial.printf("mqtt cmd: %s\n", line);
  handle(line);
}
/* THE CLOUD MUST NEVER STALL THE LAN. 13:37 on 2026-09-08: the local page's
 * round trip went from 60 ms to 2..11 s in bursts. PubSubClient's connect()
 * blocks the whole loop for its socket timeout (15 s default) and resolves
 * the broker's name every time; with the WAN link hiccuping, that ran every
 * 5 s while the relays and HTTP waited behind it. Now: 2 s socket timeout,
 * the broker resolved once per link and reused, 60 s keepalive, and a
 * failed attempt backs off 30 s. stall= in STATUS is the longest loop gap
 * since the last STATUS, so this can be seen instead of guessed. */
static void mqttTry() {
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;
  uint32_t t0 = millis();
  if (mqtt_ip == IPAddress((uint32_t)0)) {
    if (!WiFi.hostByName(MQTT_HOST, mqtt_ip) || mqtt_ip == IPAddress((uint32_t)0)) {
      Serial.printf("mqtt: dns failed (%lu ms)\n", (unsigned long)(millis() - t0));
      mqtt_next = millis() + 30000; return;
    }
  }
  mqtt.setServer(mqtt_ip, MQTT_PORT);
  mqtt.setSocketTimeout(2);
  mqtt.setKeepAlive(60);
  mqtt.setCallback(mqttCallback);
  if (mqtt.connect(DEVICE_ID, T("status").c_str(), 1, true, "offline")) {
    mqtt.subscribe(T("cmd").c_str(), 1);
    status();
    Serial.printf("mqtt: connected in %lu ms\n", (unsigned long)(millis() - t0));
  } else {
    Serial.printf("mqtt: connect failed rc=%d after %lu ms - next try in 30 s\n", mqtt.state(), (unsigned long)(millis() - t0));
    mqtt_next = millis() + 30000;
  }
}

void setup() {
  for (int i = 0; i < 4; i++) { pinMode(RELAY_PIN[i], OUTPUT); digitalWrite(RELAY_PIN[i], LOW); }
  for (int i = 0; i < 4; i++) pinMode(KEY_PIN[i], INPUT_PULLUP);
  Serial.begin(115200);
  delay(200);
  Serial.println("HS300 relay box ready, all open. topics relay/" DEVICE_ID "/cmd|reply|ev|status");
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  httpd.on("/",       HTTP_GET, httpRoot);
  httpd.on("/cmd",    HTTP_GET, httpCmd);
  httpd.on("/ui",     HTTP_GET, []() { httpd.send_P(200, "text/html", UI_HTML); });
  httpd.on("/status", HTTP_GET, httpStatus);
  httpd.begin();
  wifiTry();
  localTry();
  mqttTry();
}

static char line[48]; static uint8_t n = 0;

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { line[n] = 0; if (n) handle(line); n = 0; }
    else if (n < sizeof(line) - 1) line[n++] = c;
  }
  uint32_t now = millis();
  if (loop_last && now - loop_last > stall_max) stall_max = now - loop_last;
  loop_last = now;
  for (int i = 0; i < 4; i++) {
    if (off_at[i] && (int32_t)(now - off_at[i]) >= 0) { set_relay(i, false, 0); status(); }
    uint8_t k = digitalRead(KEY_PIN[i]);
    if (k != key_last[i] && now - key_ms[i] > 50) {      /* debounced edge */
      key_last[i] = k; key_ms[i] = now;
      if (k == 0) { set_relay(i, !st[i], 0); status(); } /* press toggles */
    }
  }
  httpd.handleClient();
  if (ota_up) ArduinoOTA.handle();
  if (mqtt.connected()) mqtt.loop();
  if ((int32_t)(now - wifi_next) >= 0) {
    wifi_next = now + 15000;
    if (WiFi.status() != WL_CONNECTED) mqtt_ip = IPAddress((uint32_t)0);   /* re-resolve on a new link */
    wifiTry(); localTry();
  }
  if ((int32_t)(now - mqtt_next) >= 0) { mqtt_next = now + 5000;  mqttTry(); }
}
