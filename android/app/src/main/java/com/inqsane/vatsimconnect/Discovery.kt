package com.inqsane.vatsimconnect

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.Inet4Address
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.URL

data class DiscoverResult(
    val hosts: List<String>,
    val wsPort: Int,
    val httpPort: Int
)

object Discovery {
    private const val UDP_PORT = 39273

    suspend fun find(code: String): DiscoverResult? = withContext(Dispatchers.IO) {
        val payload = JSONObject()
            .put("action", "discover")
            .put("code", code.uppercase().replace(" ", ""))
            .toString()
            .toByteArray(Charsets.UTF_8)

        DatagramSocket().use { socket ->
            socket.broadcast = true
            socket.soTimeout = 1500
            val targets = broadcastTargets()
            repeat(3) {
                for (target in targets) {
                    try {
                        socket.send(DatagramPacket(payload, payload.size, target, UDP_PORT))
                    } catch (_: Exception) {
                    }
                }
                val buf = ByteArray(4096)
                val packet = DatagramPacket(buf, buf.size)
                val deadline = System.currentTimeMillis() + 1500
                while (System.currentTimeMillis() < deadline) {
                    try {
                        socket.soTimeout = (deadline - System.currentTimeMillis()).toInt().coerceAtLeast(200)
                        socket.receive(packet)
                        val text = String(packet.data, 0, packet.length, Charsets.UTF_8)
                        val json = JSONObject(text)
                        if (json.optString("action") != "discover_ok") continue
                        val hosts = linkedSetOf<String>()
                        val primary = json.optString("host")
                        if (primary.isNotBlank()) hosts.add(primary)
                        val arr: JSONArray? = json.optJSONArray("ips")
                        if (arr != null) {
                            for (i in 0 until arr.length()) {
                                val ip = arr.optString(i)
                                if (ip.isNotBlank()) hosts.add(ip)
                            }
                        }
                        val replyIp = packet.address?.hostAddress
                        if (!replyIp.isNullOrBlank()) hosts.add(replyIp)
                        if (hosts.isNotEmpty()) {
                            return@withContext DiscoverResult(
                                hosts = hosts.toList(),
                                wsPort = json.optInt("port", 39272),
                                httpPort = json.optInt("http_port", 39274)
                            )
                        }
                    } catch (_: Exception) {
                    }
                }
            }
        }
        null
    }

    fun manual(host: String, httpPort: Int = 39274): DiscoverResult {
        return DiscoverResult(hosts = listOf(host.trim()), wsPort = 39272, httpPort = httpPort)
    }

    fun pickReachable(hosts: List<String>, httpPort: Int): String? {
        for (host in hosts) {
            if (probeHttp(host, httpPort)) return host
        }
        for (host in hosts) {
            if (probeTcp(host, httpPort)) return host
        }
        return null
    }

    private fun broadcastTargets(): List<InetAddress> {
        val out = linkedSetOf<InetAddress>()
        try {
            out.add(InetAddress.getByName("255.255.255.255"))
        } catch (_: Exception) {
        }
        try {
            val en = NetworkInterface.getNetworkInterfaces()
            while (en.hasMoreElements()) {
                val nif = en.nextElement()
                if (!nif.isUp || nif.isLoopback) continue
                for (ifaceAddr in nif.interfaceAddresses) {
                    val b = ifaceAddr.broadcast
                    if (b != null) out.add(b)
                    val addr = ifaceAddr.address
                    if (addr is Inet4Address) {
                        val parts = addr.hostAddress.split(".")
                        if (parts.size == 4) {
                            try {
                                out.add(InetAddress.getByName("${parts[0]}.${parts[1]}.${parts[2]}.255"))
                            } catch (_: Exception) {
                            }
                        }
                    }
                }
            }
        } catch (_: Exception) {
        }
        return out.toList()
    }

    private fun probeHttp(host: String, port: Int): Boolean {
        return try {
            val conn = URL("http://$host:$port/health").openConnection() as HttpURLConnection
            conn.connectTimeout = 1500
            conn.readTimeout = 1500
            conn.requestMethod = "GET"
            val code = conn.responseCode
            conn.disconnect()
            code == 200
        } catch (_: Exception) {
            false
        }
    }

    private fun probeTcp(host: String, port: Int): Boolean {
        return try {
            java.net.Socket().use { sock ->
                sock.connect(InetSocketAddress(host, port), 1500)
                true
            }
        } catch (_: Exception) {
            false
        }
    }
}
