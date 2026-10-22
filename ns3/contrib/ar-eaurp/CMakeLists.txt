# AR-EAURP: Adversarial-Resilient, Energy-harvesting-Aware Ubiquitous Routing
# Protocol -- ns-3 contrib module.

find_package(OpenSSL REQUIRED COMPONENTS Crypto)

build_lib(
  LIBNAME ar-eaurp
  SOURCE_FILES
    model/ar-eaurp-packet.cc
    model/ar-eaurp-rtable.cc
    model/ar-eaurp-neighbor.cc
    model/ar-eaurp-nnet.cc
    model/ar-eaurp-detector.cc
    model/ar-eaurp-forecaster.cc
    model/ar-eaurp-cmdp.cc
    model/ar-eaurp-tabular.cc
    model/ar-eaurp-crypto.cc
    model/ar-eaurp-scenario.cc
    model/ar-eaurp-experiments.cc
    model/ar-eaurp-results.cc
    model/ar-eaurp-oracle.cc
    model/ar-eaurp-routing-protocol.cc
    model/solar-energy-harvester.cc
    model/ar-traffic-app.cc
    helper/ar-eaurp-helper.cc
    helper/ar-traffic-helper.cc
  HEADER_FILES
    model/ar-eaurp-packet.h
    model/ar-eaurp-rtable.h
    model/ar-eaurp-neighbor.h
    model/ar-eaurp-nnet.h
    model/ar-eaurp-detector.h
    model/ar-eaurp-forecaster.h
    model/ar-eaurp-cmdp.h
    model/ar-eaurp-tabular.h
    model/ar-eaurp-crypto.h
    model/ar-eaurp-scenario.h
    model/ar-eaurp-experiments.h
    model/ar-eaurp-results.h
    model/ar-eaurp-oracle.h
    model/ar-eaurp-routing-protocol.h
    model/solar-energy-harvester.h
    model/ar-traffic-app.h
    helper/ar-eaurp-helper.h
    helper/ar-traffic-helper.h
  LIBRARIES_TO_LINK
    OpenSSL::Crypto
    ${CMAKE_DL_LIBS}
    ${libcore}
    ${libnetwork}
    ${libinternet}
    ${libwifi}
    ${libmobility}
    ${libpropagation}
    ${libenergy}
    ${libapplications}
    ${libaodv}
    ${libflow-monitor}
    ${libstats}
  TEST_SOURCES
    test/ar-eaurp-test-suite.cc
)
