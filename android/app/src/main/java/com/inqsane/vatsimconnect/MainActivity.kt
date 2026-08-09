package com.inqsane.vatsimconnect

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.inqsane.vatsimconnect.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding

    private val notifPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                BridgeService.ACTION_STATUS -> {
                    val text = intent.getStringExtra(BridgeService.EXTRA_TEXT).orEmpty()
                    binding.footerStatus.text = text
                    if (
                        text == "Linked" ||
                        text.startsWith("Online") ||
                        text.startsWith("VATSIM") ||
                        text.startsWith("Waiting for VATSIM")
                    ) {
                        showLive(text)
                    }
                    if (
                        text.contains("Invalid", true) ||
                        text.contains("Unknown", true) ||
                        text.contains("failed", true) ||
                        text.contains("error", true)
                    ) {
                        Toast.makeText(this@MainActivity, text, Toast.LENGTH_LONG).show()
                    }
                }
                BridgeService.ACTION_MESSAGE -> {
                    val from = intent.getStringExtra(BridgeService.EXTRA_FROM).orEmpty()
                    val body = intent.getStringExtra(BridgeService.EXTRA_BODY).orEmpty()
                    binding.lastMessage.text = "$from\n$body"
                    showLive(null)
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        NotifyHelper.ensureChannels(this)
        askNotifications()

        binding.pairButton.setOnClickListener { pair() }
        binding.unpairButton.setOnClickListener { unpair() }

        if (!Prefs.token(this).isNullOrBlank()) {
            showLive(getString(R.string.waiting))
            ContextCompat.startForegroundService(
                this,
                Intent(this, BridgeService::class.java)
                    .putExtra(BridgeService.EXTRA_MODE, BridgeService.MODE_RESUME)
            )
        } else {
            showPair()
        }
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter().apply {
            addAction(BridgeService.ACTION_STATUS)
            addAction(BridgeService.ACTION_MESSAGE)
        }
        ContextCompat.registerReceiver(this, receiver, filter, ContextCompat.RECEIVER_NOT_EXPORTED)
    }

    override fun onStop() {
        unregisterReceiver(receiver)
        super.onStop()
    }

    private fun askNotifications() {
        if (Build.VERSION.SDK_INT >= 33) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    private fun pair() {
        val code = binding.codeInput.text?.toString()?.trim().orEmpty().uppercase()
            .replace(" ", "")
        if (code.length != 6) {
            Toast.makeText(this, "Enter the 6-character code", Toast.LENGTH_SHORT).show()
            return
        }
        val manualIp = binding.ipInput.text?.toString()?.trim().orEmpty()
        binding.pairButton.isEnabled = false
        binding.footerStatus.text = if (manualIp.isBlank()) "Searching on Wi-Fi…" else "Connecting to $manualIp…"
        lifecycleScope.launch {
            val found = if (manualIp.isNotBlank()) {
                Discovery.manual(manualIp)
            } else {
                Discovery.find(code)
            }
            if (found == null) {
                binding.pairButton.isEnabled = true
                binding.footerStatus.text = "No PC found. Enter PC IP from the Windows app."
                Toast.makeText(this@MainActivity, "Could not find Windows app", Toast.LENGTH_LONG).show()
                return@launch
            }
            binding.footerStatus.text = "Checking connection…"
            val host = withContext(Dispatchers.IO) {
                Discovery.pickReachable(found.hosts, found.httpPort)
            }
            if (host.isNullOrBlank()) {
                binding.pairButton.isEnabled = true
                binding.footerStatus.text = "PC unreachable. Check IP / firewall."
                Toast.makeText(
                    this@MainActivity,
                    "Could not reach PC on port ${found.httpPort}",
                    Toast.LENGTH_LONG
                ).show()
                return@launch
            }
            binding.footerStatus.text = "Connecting to $host…"
            val intent = Intent(this@MainActivity, BridgeService::class.java)
                .putExtra(BridgeService.EXTRA_MODE, BridgeService.MODE_PAIR)
                .putExtra(BridgeService.EXTRA_CODE, code)
                .putExtra(BridgeService.EXTRA_HOST, host)
                .putExtra(BridgeService.EXTRA_HTTP_PORT, found.httpPort)
            ContextCompat.startForegroundService(this@MainActivity, intent)
            binding.pairButton.isEnabled = true
        }
    }

    private fun unpair() {
        startService(
            Intent(this, BridgeService::class.java)
                .putExtra(BridgeService.EXTRA_MODE, BridgeService.MODE_STOP)
        )
        Prefs.clear(this)
        showPair()
        binding.footerStatus.text = getString(R.string.status_idle)
        binding.lastMessage.text = ""
    }

    private fun showPair() {
        binding.pairPanel.visibility = View.VISIBLE
        binding.livePanel.visibility = View.GONE
    }

    private fun showLive(statusText: String?) {
        binding.pairPanel.visibility = View.GONE
        binding.livePanel.visibility = View.VISIBLE
        if (!statusText.isNullOrBlank()) {
            binding.liveStatus.text = statusText
        } else if (binding.liveStatus.text.isNullOrBlank()) {
            binding.liveStatus.text = getString(R.string.waiting)
        }
    }
}
