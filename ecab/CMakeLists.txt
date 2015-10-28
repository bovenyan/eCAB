cmake_minimum_required(VERSION 2.8) 
project(CAB_SDN)

set(CMAKE_CXX_COMPILER /usr/bin/g++)
set(CMAKE_CXX_FLAGS "-std=c++11 -g")

find_package(Boost 1.54.0 REQUIRED COMPONENTS system thread filesystem iostreams log log_setup)
if(Boost_FOUND)
	message(STATUS "Boost found")
	message(STATUS "BOOST_LIBRARIES: " ${Boost_LIBRARIES})
    add_definitions(-DBOOST_LOG_DYN_LINK)
endif()
set(libcab_include "../../CAB_SDN")
set(libcab_lib "/home/bovenyan/Documents/CAB_SDN/build/libcab.a")
include_directories(./)
include_directories(${libcab_include})

add_executable(CABDaemon CABDaemon.cpp)
#add_executable(CMRDaemon CMRDaemon.cpp)

#add_executable(FlowGen FlowGen.cpp)
#add_executable(FlowGen2 FlowGen2.cpp)
#add_executable(FlowGen3 FlowGen3.cpp)

if(UNIX)
	target_link_libraries(
		CABDaemon
        ${libcab_lib}
		${Boost_LIBRARIES}
		pthread
		)

elseif(WIN32)
elseif(APPLE)
endif(UNIX)

message(STATUS "c++ flag : " ${CMAKE_CXX_FLAGS}) 
message(STATUS "this is source dir " ${PROJECT_SOURCE_DIR})
message(STATUS "this is binary dir " ${PROJECT_BINARY_DIR})
