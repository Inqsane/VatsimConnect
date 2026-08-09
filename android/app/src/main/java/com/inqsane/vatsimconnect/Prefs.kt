package com.inqsane.vatsimconnect

import android.content.Context

object Prefs {
    private const val NAME = "vatsim_connect"
    private const val KEY_TOKEN = "token"
    private const val KEY_HOST = "host"
    private const val KEY_PORT = "port"

    fun token(ctx: Context): String? =
        ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE).getString(KEY_TOKEN, null)

    fun host(ctx: Context): String? =
        ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE).getString(KEY_HOST, null)

    fun port(ctx: Context): Int =
        ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE).getInt(KEY_PORT, 39274)

    fun save(ctx: Context, token: String, host: String, port: Int) {
        ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE).edit()
            .putString(KEY_TOKEN, token)
            .putString(KEY_HOST, host)
            .putInt(KEY_PORT, port)
            .apply()
    }

    fun clear(ctx: Context) {
        ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE).edit().clear().apply()
    }
}
