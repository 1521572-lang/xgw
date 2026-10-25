cmake_minimum_required(VERSION 3.22.1)
project(xgwrun C)

# Запуск Xray процессом с дескриптором VPN (А3): см. xgwrun.c.
add_library(xgwrun SHARED xgwrun.c)
target_compile_options(xgwrun PRIVATE -Wall -Wextra -Werror)
