package net.xgw.android

/** Запуск Xray процессом с дескриптором VPN — src/main/cpp/xgwrun.c. */
object Native {
    init {
        System.loadLibrary("xgwrun")
    }

    /** pid процесса; меньше 0 — -errno. argv[0] — исполняемый файл. Дескриптор [tun] у Xray — номер 3. */
    @JvmStatic external fun start(argv: Array<String>, envp: Array<String>, tun: Int, log: String): Int

    /** Ждёт конца процесса: код выхода, сигнал — 128 + номер. Вызывать из того же потока, что [start]. */
    @JvmStatic external fun waitFor(pid: Int): Int

    /** SIGTERM процессу. */
    @JvmStatic external fun stop(pid: Int): Int
}
