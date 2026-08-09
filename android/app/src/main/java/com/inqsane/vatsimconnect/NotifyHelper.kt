package com.inqsane.vatsimconnect

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat

object NotifyHelper {
    const val CHANNEL_LIVE = "vatsim_live"
    const val CHANNEL_ATC = "vatsim_atc"
    const val LIVE_ID = 42

    fun ensureChannels(ctx: Context) {
        val manager = ctx.getSystemService(NotificationManager::class.java)
        val live = NotificationChannel(
            CHANNEL_LIVE,
            "Connection",
            NotificationManager.IMPORTANCE_LOW
        )
        live.description = "Keeps the bridge alive"
        val atc = NotificationChannel(
            CHANNEL_ATC,
            "ATC Messages",
            NotificationManager.IMPORTANCE_HIGH
        )
        atc.description = "Incoming vPilot ATC text"
        atc.enableVibration(true)
        manager.createNotificationChannel(live)
        manager.createNotificationChannel(atc)
    }

    fun liveNotification(ctx: Context, text: String, callsign: String? = null): Notification {
        val open = PendingIntent.getActivity(
            ctx,
            0,
            Intent(ctx, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val title = if (!callsign.isNullOrBlank()) {
            "VatsimConnect · $callsign"
        } else {
            "VatsimConnect"
        }
        return NotificationCompat.Builder(ctx, CHANNEL_LIVE)
            .setContentTitle(title)
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentIntent(open)
            .setOngoing(true)
            .setSilent(true)
            .build()
    }

    fun atcNotification(ctx: Context, from: String, body: String) {
        val manager = ctx.getSystemService(NotificationManager::class.java)
        val open = PendingIntent.getActivity(
            ctx,
            1,
            Intent(ctx, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val note = NotificationCompat.Builder(ctx, CHANNEL_ATC)
            .setContentTitle(from)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentIntent(open)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .build()
        manager.notify((System.currentTimeMillis() % Int.MAX_VALUE).toInt(), note)
    }
}
