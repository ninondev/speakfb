// SPDX-License-Identifier: GPL-3.0-only
// Copyright (c) 2026 Ninon
// Transcribe audio on this Mac with word times and confidence.
// Output: start seconds, end seconds, confidence, word (tab-separated).
import Foundation
import Speech
import AVFoundation

@main
struct SpeakFeedback {
    static func main() async {
        let args = CommandLine.arguments
        guard args.count == 2 || (args.count == 4 && args[2] == "--locale") else {
            print("usage: speakfb <audio.wav> [--locale en-US]")
            return
        }
        let locale = args.count == 4 ? args[3] : "en-US"
        do {
            let transcriber = SpeechTranscriber(locale: Locale(identifier: locale),
                                                transcriptionOptions: [],
                                                reportingOptions: [],
                                                attributeOptions: [.audioTimeRange, .transcriptionConfidence])
            if let req = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
                try await req.downloadAndInstall()
            }
            let file = try AVAudioFile(forReading: URL(fileURLWithPath: args[1]))
            let collector = Task { () -> [String] in
                var lines: [String] = []
                for try await r in transcriber.results {
                    for run in r.text.runs {
                        let word = String(r.text[run.range].characters).trimmingCharacters(in: .whitespaces)
                        if word.isEmpty { continue }
                        let tr = run.audioTimeRange
                        let s = tr.map { $0.start.seconds } ?? -1
                        let e = tr.map { $0.end.seconds } ?? -1
                        let c = run.transcriptionConfidence ?? -1
                        lines.append(String(format: "%.2f\t%.2f\t%.2f\t", s, e, c) + word)
                    }
                }
                return lines
            }
            let analyzer = SpeechAnalyzer(modules: [transcriber])
            if let last = try await analyzer.analyzeSequence(from: file) {
                try await analyzer.finalizeAndFinish(through: last)
            } else {
                await analyzer.cancelAndFinishNow()
            }
            for l in try await collector.value { print(l) }
        } catch {
            print("ERROR:", error)
        }
    }
}
