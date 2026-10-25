/*
 * Запуск Xray отдельным процессом с дескриптором VPN (А3, ANDROID_APP_PLAN.md).
 *
 * Java при запуске процесса (ProcessBuilder) закрывает все дескрипторы, кроме 0–2, и
 * дескриптор интерфейса VpnService до Xray не дошёл бы. Здесь — fork и execve: дескриптор
 * TUN становится номером 3 (XRAY_TUN_FD=3), вывод Xray — в файл журнала, остальные
 * дескрипторы приложения закрываются. Всё, что нужно процессу, готовится до fork: после
 * него в дочернем процессе — только вызовы, безопасные между fork и exec.
 *
 * Xray умирает вместе с потоком приложения, который его запустил (PR_SET_PDEATHSIG): поток
 * живёт, пока ждёт Xray (waitFor), — иначе после гибели приложения Xray держал бы
 * интерфейс VPN без хозяина.
 */

#include <errno.h>
#include <fcntl.h>
#include <jni.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#define TUN_FD 3

static void release(char **list) {
    if (list == NULL) return;
    for (char **item = list; *item != NULL; item++) free(*item);
    free(list);
}

/* String[] Java → массив строк C с NULL в конце; NULL — не хватило памяти. */
static char **strings(JNIEnv *env, jobjectArray array) {
    jsize count = (*env)->GetArrayLength(env, array);
    char **list = calloc((size_t) count + 1, sizeof(char *));
    if (list == NULL) return NULL;
    for (jsize i = 0; i < count; i++) {
        jstring item = (jstring) (*env)->GetObjectArrayElement(env, array, i);
        const char *text = (*env)->GetStringUTFChars(env, item, NULL);
        list[i] = text != NULL ? strdup(text) : NULL;
        if (text != NULL) (*env)->ReleaseStringUTFChars(env, item, text);
        (*env)->DeleteLocalRef(env, item);
        if (list[i] == NULL) {
            release(list);
            return NULL;
        }
    }
    return list;
}

/*
 * Native.start(argv, envp, tunFd, logPath): pid процесса Xray, меньше 0 — -errno.
 * argv[0] — путь к исполняемому файлу.
 */
JNIEXPORT jint JNICALL
Java_net_xgw_android_Native_start(JNIEnv *env, jclass cls, jobjectArray args, jobjectArray envs,
                                  jint tun, jstring logPath) {
    (void) cls;
    char **argv = strings(env, args);
    char **envp = strings(env, envs);
    const char *path = (*env)->GetStringUTFChars(env, logPath, NULL);
    if (argv == NULL || argv[0] == NULL || envp == NULL || path == NULL) {
        release(argv);
        release(envp);
        if (path != NULL) (*env)->ReleaseStringUTFChars(env, logPath, path);
        return -ENOMEM;
    }
    int log = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    int saved = errno;
    (*env)->ReleaseStringUTFChars(env, logPath, path);
    /* Копия TUN — номером выше 3: dup2 на тот же номер не сняла бы FD_CLOEXEC. */
    int copy = log < 0 ? -1 : fcntl(tun, F_DUPFD_CLOEXEC, 10);
    if (log < 0 || copy < 0) {
        if (copy < 0 && log >= 0) saved = errno;
        if (log >= 0) close(log);
        release(argv);
        release(envp);
        return -saved;
    }
    struct rlimit limit;
    long top = getrlimit(RLIMIT_NOFILE, &limit) == 0 && limit.rlim_cur != RLIM_INFINITY
        ? (long) limit.rlim_cur : 4096;
    if (top > 65536) top = 65536;
    pid_t parent = getpid();

    pid_t pid = fork();
    if (pid == 0) {
        sigset_t all;
        sigemptyset(&all);
        sigprocmask(SIG_SETMASK, &all, NULL);
        prctl(PR_SET_PDEATHSIG, SIGKILL);
        if (getppid() != parent) _exit(125); /* приложение уже умерло */
        int null = open("/dev/null", O_RDONLY);
        if (null < 0 || dup2(null, 0) < 0 || dup2(log, 1) < 0 || dup2(log, 2) < 0 ||
            dup2(copy, TUN_FD) < 0) {
            _exit(126);
        }
        for (int fd = TUN_FD + 1; fd < top; fd++) close(fd);
        execve(argv[0], argv, envp);
        _exit(127);
    }
    saved = errno;
    close(copy);
    close(log);
    release(argv);
    release(envp);
    return pid > 0 ? pid : -saved;
}

/* Native.waitFor(pid): ждёт конца Xray; код выхода, сигнал — 128 + номер, ошибка — -errno. */
JNIEXPORT jint JNICALL
Java_net_xgw_android_Native_waitFor(JNIEnv *env, jclass cls, jint pid) {
    (void) env;
    (void) cls;
    int status = 0;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR) return -errno;
    }
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    if (WIFSIGNALED(status)) return 128 + WTERMSIG(status);
    return -1;
}

/* Native.stop(pid): попросить Xray завершиться (SIGTERM). */
JNIEXPORT jint JNICALL
Java_net_xgw_android_Native_stop(JNIEnv *env, jclass cls, jint pid) {
    (void) env;
    (void) cls;
    return kill(pid, SIGTERM) == 0 ? 0 : -errno;
}
