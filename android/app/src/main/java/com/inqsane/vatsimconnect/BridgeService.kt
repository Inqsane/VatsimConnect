package com.inqsane.vatsimconnect

import android.app.Service
import android.content.Intent
import android.os.IBinder
import org.json.JSONObject
import java.io.BufferedOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

class BridgeService : Service() {
    companion object {
        const val ACTION_STATUS = "com.inqsane.vatsimconnect.STATUS"
        const val ACTION_MESSAGE = "com.inqsane.vatsimconnect.MESSAGE"
        const val EXTRA_TEXT = "text"
        const val EXTRA_FROM = "from"
        const val EXTRA_BODY = "body"
        const val EXTRA_KIND = "kind"
        const val EXTRA_MODE = "mode"
        const val EXTRA_CODE = "code"
        const val EXTRA_HOST = "host"
        const val EXTRA_PORT = "port"
        const val EXTRA_HTTP_PORT = "http_port"
        const val MODE_PAIR = "pair"
        const val MODE_RESUME = "resume"
        const val MODE_STOP = "stop"
    }

    private val running = AtomicBoolean(false)
    private var worker: Thread? = null
    private var lastCallsign: String? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        NotifyHelper.ensureChannels(this)
        startForeground(NotifyHelper.LIVE_ID, NotifyHelper.liveNotification(this, "Starting…"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val mode = intent?.getStringExtra(EXTRA_MODE) ?: MODE_RESUME
        if (mode == MODE_STOP) {
            stopSelfSafe()
            return START_NOT_STICKY
        }
        if (running.getAndSet(true)) {
            return START_STICKY
        }
        when (mode) {
            MODE_PAIR -> {
                val code = intent?.getStringExtra(EXTRA_CODE).orEmpty()
                val host = intent?.getStringExtra(EXTRA_HOST).orEmpty()
                val httpPort = intent?.getIntExtra(EXTRA_HTTP_PORT, 39274) ?: 39274
                worker = thread(name = "vc-pair") {
                    try {
                        pairAndListen(host, httpPort, code)
                    } catch (ex: Exception) {
                        publishStatus(ex.message ?: "Pair failed")
                        stopSelfSafe()
                    }
                }
            }
            else -> {
                val host = Prefs.host(this)
                val token = Prefs.token(this)
                val httpPort = Prefs.port(this)
                if (host.isNullOrBlank() || token.isNullOrBlank()) {
                    publishStatus("Not paired")
                    stopSelfSafe()
                } else {
                    worker = thread(name = "vc-resume") {
                        try {
                            resumeAndListen(host, httpPort, token)
                        } catch (ex: Exception) {
                            publishStatus(ex.message ?: "Resume failed")
                            stopSelfSafe()
                        }
                    }
                }
            }
        }
        return START_STICKY
    }

    private fun pairAndListen(host: String, httpPort: Int, code: String) {
        updateLive("Pairing with $host…")
        publishStatus("Pairing with $host…")
        val body = JSONObject()
            .put("code", code.uppercase())
            .put("name", android.os.Build.MODEL)
            .toString()
        val response = httpPost("http://$host:$httpPort/pair", body)
        val json = JSONObject(response)
        if (json.optString("type") == "error") {
            publishStatus(json.optString("message", "Pair failed"))
            stopSelfSafe()
            return
        }
        val token = json.optString("token")
        if (token.isBlank()) {
            publishStatus("No token from PC")
            stopSelfSafe()
            return
        }
        Prefs.save(this, token, host, httpPort)
        handlePayload(json)
        listenLoop(host, httpPort, token)
    }

    private fun resumeAndListen(host: String, httpPort: Int, token: String) {
        updateLive("Reconnecting…")
        val body = JSONObject().put("token", token).toString()
        val response = httpPost("http://$host:$httpPort/resume", body)
        val json = JSONObject(response)
        if (json.optString("type") == "error") {
            publishStatus(json.optString("message", "Resume failed"))
            stopSelfSafe()
            return
        }
        handlePayload(json)
        listenLoop(host, httpPort, token)
    }

    private fun listenLoop(host: String, httpPort: Int, token: String) {
        while (running.get()) {
            try {
                val url = "http://$host:$httpPort/wait?token=${java.net.URLEncoder.encode(token, "UTF-8")}"
                val raw = httpGet(url, connectMs = 3000, readMs = 8000)
                val json = JSONObject(raw)
                handlePayload(json)
            } catch (_: Exception) {
                if (!running.get()) break
                publishStatus("Reconnecting…")
                updateLive("Reconnecting…")
                try {
                    Thread.sleep(1500)
                } catch (_: InterruptedException) {
                    break
                }
            }
        }
    }

    private fun handlePayload(json: JSONObject) {
        when (json.optString("type")) {
            "message" -> {
                val from = json.optString("from", "ATC")
                val body = json.optString("body", "")
                val kind = json.optString("kind", "private")
                NotifyHelper.atcNotification(this, from, body)
                sendBroadcast(
                    Intent(ACTION_MESSAGE)
                        .setPackage(packageName)
                        .putExtra(EXTRA_FROM, from)
                        .putExtra(EXTRA_BODY, body)
                        .putExtra(EXTRA_KIND, kind)
                )
            }
            "status", "resumed", "paired" -> {
                val callsign = readCallsign(json)
                val connected = json.optBoolean("connected", false)
                if (callsign.isNotBlank()) {
                    lastCallsign = callsign
                }
                val shown = callsign.ifBlank { lastCallsign.orEmpty() }
                val text = if (connected && shown.isNotBlank()) {
                    "Online as $shown"
                } else if (connected) {
                    "Online"
                } else if (json.optString("type") == "paired" || json.optString("type") == "resumed") {
                    if (shown.isNotBlank()) "Linked · $shown" else "Linked"
                } else if (shown.isNotBlank()) {
                    "Waiting for VATSIM · $shown"
                } else {
                    "Waiting for VATSIM"
                }
                updateLive(text)
                publishStatus(text)
            }
            "error" -> publishStatus(json.optString("message", "Error"))
        }
    }

    private fun readCallsign(json: JSONObject): String {
        if (!json.has("callsign") || json.isNull("callsign")) return ""
        val raw = json.optString("callsign", "").trim()
        if (raw.isEmpty() || raw.equals("null", true) || raw.equals("none", true)) return ""
        return raw
    }

    private fun httpPost(url: String, body: String): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 4000
        conn.readTimeout = 4000
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json")
        BufferedOutputStream(conn.outputStream).use { out ->
            out.write(body.toByteArray(Charsets.UTF_8))
            out.flush()
        }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val text = stream?.bufferedReader()?.readText().orEmpty()
        conn.disconnect()
        if (code !in 200..299 && text.isBlank()) {
            throw IllegalStateException("HTTP $code")
        }
        return text
    }

    private fun httpGet(url: String, connectMs: Int, readMs: Int): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = connectMs
        conn.readTimeout = readMs
        conn.requestMethod = "GET"
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val text = stream?.bufferedReader()?.readText().orEmpty()
        conn.disconnect()
        if (code !in 200..299) {
            throw IllegalStateException("HTTP $code")
        }
        return text
    }

    private fun updateLive(text: String) {
        val manager = getSystemService(NOTIFICATION_SERVICE) as android.app.NotificationManager
        manager.notify(NotifyHelper.LIVE_ID, NotifyHelper.liveNotification(this, text, lastCallsign))
    }

    private fun publishStatus(text: String) {
        sendBroadcast(
            Intent(ACTION_STATUS)
                .setPackage(packageName)
                .putExtra(EXTRA_TEXT, text)
        )
    }

    private fun stopSelfSafe() {
        running.set(false)
        try {
            worker?.interrupt()
        } catch (_: Exception) {
        }
        worker = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        running.set(false)
        super.onDestroy()
    }
}
