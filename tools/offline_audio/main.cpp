// Headless local adapter. Audio decoding and MIDI writing belong to the workbench.
#include "muscriptor/muscriptor.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
#include <algorithm>
#include <thread>
#include <chrono>
#include <string>
#include <windows.h>
#include <psapi.h>
#ifdef _MSC_VER
#include <intrin.h>
#endif

int wmain(int argc, wchar_t** argv) {
    if (argc < 4 || argc > 5) {
        std::cerr << "Usage: nte-audio MODEL.gguf MONO_16000.f32 NOTES.json [threads]\n";
        return 2;
    }
    try {
#ifdef _MSC_VER
        int cpu[4]; __cpuid(cpu, 1);
        const unsigned required = (1u << 20) | (1u << 27) | (1u << 28) | (1u << 29);
        if ((unsigned(cpu[2]) & required) != required || (_xgetbv(0) & 6) != 6)
            throw std::runtime_error("The song engine needs an x64 CPU with AVX/F16C support");
#endif
        const auto pcm = std::filesystem::path(argv[2]);
        const auto size = std::filesystem::file_size(pcm);
        if (size % sizeof(float) || size > 16000ULL * 3600 * 4)
            throw std::runtime_error("Invalid PCM size (limit: one hour)");
        std::vector<float> samples(size / sizeof(float));
        std::ifstream input(pcm, std::ios::binary);
        if (!input.read(reinterpret_cast<char*>(samples.data()), size))
            throw std::runtime_error("Cannot read audio");
        const auto started = std::chrono::steady_clock::now();
        const auto elapsed = [&] { return std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count(); };
        msl::LoadOptions loading;
        loading.device = msl::availableDevices().size() - 1;
        auto transcriber = msl::Transcriber::load(std::filesystem::path(argv[1]), loading);
        if (!transcriber) throw std::runtime_error(msl::describe(transcriber.error()));
        const auto loaded = elapsed();
        const auto& device = transcriber->device();
        std::cerr << "device=" << device.name << "; backend=" << device.backend << "; load_seconds=" << loaded << '\n';
        msl::TranscribeOptions options;
        // Too many threads slows token-by-token decoding. Leave capacity for the UI.
        options.n_threads = std::clamp(int(std::thread::hardware_concurrency()) / 2, 1, 8);
        if (argc == 5) options.n_threads = std::clamp(std::stoi(argv[4]), 1, 16);
        std::cout << "{\"backend\":\"" << device.backend << "\",\"threads\":" << options.n_threads << "}\n" << std::flush;
        auto notes = transcriber->transcribe(samples, options, [](const auto& update) {
            std::cout << "{\"progress\":" << update.progress << "}\n" << std::flush;
            return true;
        });
        if (!notes) throw std::runtime_error(msl::describe(notes.error()));
        PROCESS_MEMORY_COUNTERS memory{};
        GetProcessMemoryInfo(GetCurrentProcess(), &memory, sizeof(memory));
        std::cout << "{\"native_seconds\":" << elapsed() << ",\"load_seconds\":" << loaded
                  << ",\"peak_working_set_bytes\":" << memory.PeakWorkingSetSize << "}\n" << std::flush;
        std::ofstream output(std::filesystem::path(argv[3]), std::ios::binary);
        output.precision(9);
        output << "[";
        bool first = true;
        for (const auto& n : *notes) {
            if (!first) output << ",";
            first = false;
            output << "{\"start\":" << n.onset << ",\"end\":" << n.offset
                   << ",\"pitch\":" << n.pitch << ",\"program\":" << n.program
                   << ",\"drum\":" << (n.is_drum ? "true" : "false") << "}";
        }
        output << "]\n";
        if (!output) throw std::runtime_error("Cannot write notes");
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
