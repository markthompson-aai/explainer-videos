---
title: How streaming speech-to-text works
subtitle: What happens between someone speaking and words appearing on screen, usually in well under a second
voice: aai-anna
---

## How streaming speech-to-text works
```slide
@layout title
```
This is a short explainer on how streaming speech to text works: what happens between someone speaking into a microphone and words appearing on a screen, usually in well under a second.

We'll walk through the pipeline, how the model handles audio it hasn't finished hearing yet, the difference between partial and final transcripts, where the latency comes from, and what tends to hurt accuracy. It takes about four minutes.

## The pipeline, end to end
```slide
<div class="flow">
  <div class="box"><b>Microphone</b><small>16 kHz, 16-bit PCM</small></div><span class="arrow"></span>
  <div class="box"><b>Chunks</b><small>about 50 ms each</small></div><span class="arrow"></span>
  <div class="box"><b>WebSocket</b><small>one session stays open</small></div><span class="arrow"></span>
  <div class="box accent"><b>Streaming model</b><small>encoder and decoder</small></div><span class="arrow"></span>
  <div class="box"><b>Turn messages</b><small>partials, then a final</small></div>
</div>
<p class="note">Audio flows one way, text flows back on the same connection, continuously. Nothing waits for the sentence to end.</p>
```
Start with the shape of the whole thing. The microphone produces raw audio samples, typically sixteen thousand per second, each a sixteen bit number. The client groups them into small chunks, around fifty milliseconds of sound, and sends each chunk down a WebSocket as soon as it exists.

A WebSocket is just a two way connection that stays open. Audio goes up it, and transcript messages come back down the same pipe. On the server side, a streaming model consumes the chunks as they arrive and emits text as it goes.

The key difference from transcribing a file is that nothing waits. The model never gets to see the whole recording. It has to commit to words while the speaker is still talking.

## What the model actually hears
```slide
<svg viewBox="0 0 1750 450" width="1750" height="450" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="fade" x1="0" x2="1"><stop offset="0" stop-color="#f7f7fb"/><stop offset="1" stop-color="#d9d7ea"/></linearGradient>
  </defs>
  <!-- regions -->
  <rect x="40" y="70" width="900" height="200" rx="16" fill="#eceaf6"/>
  <rect x="940" y="70" width="260" height="200" rx="16" fill="#e6e2fb" stroke="#3923c7" stroke-width="5"/>
  <rect x="1200" y="70" width="130" height="200" rx="16" fill="#fff4df" stroke="#f59e0b" stroke-width="4" stroke-dasharray="14 10"/>
  <rect x="1330" y="70" width="380" height="200" rx="16" fill="url(#fade)" opacity="0.6"/>
  <!-- waveform bars -->
  <g fill="#8e88b8">
    <rect x="70" y="150" width="14" height="40"/><rect x="100" y="120" width="14" height="100"/><rect x="130" y="140" width="14" height="60"/><rect x="160" y="100" width="14" height="140"/><rect x="190" y="130" width="14" height="80"/><rect x="220" y="155" width="14" height="30"/><rect x="250" y="115" width="14" height="110"/><rect x="280" y="135" width="14" height="70"/><rect x="310" y="105" width="14" height="130"/><rect x="340" y="145" width="14" height="50"/><rect x="370" y="125" width="14" height="90"/><rect x="400" y="110" width="14" height="120"/><rect x="430" y="150" width="14" height="40"/><rect x="460" y="130" width="14" height="80"/><rect x="490" y="100" width="14" height="140"/><rect x="520" y="140" width="14" height="60"/><rect x="550" y="120" width="14" height="100"/><rect x="580" y="155" width="14" height="30"/><rect x="610" y="115" width="14" height="110"/><rect x="640" y="135" width="14" height="70"/><rect x="670" y="105" width="14" height="130"/><rect x="700" y="145" width="14" height="50"/><rect x="730" y="125" width="14" height="90"/><rect x="760" y="110" width="14" height="120"/><rect x="790" y="150" width="14" height="40"/><rect x="820" y="130" width="14" height="80"/><rect x="850" y="100" width="14" height="140"/><rect x="880" y="140" width="14" height="60"/><rect x="910" y="120" width="14" height="100"/>
  </g>
  <g fill="#3923c7">
    <rect x="960" y="120" width="14" height="100"/><rect x="990" y="100" width="14" height="140"/><rect x="1020" y="140" width="14" height="60"/><rect x="1050" y="110" width="14" height="120"/><rect x="1080" y="130" width="14" height="80"/><rect x="1110" y="105" width="14" height="130"/><rect x="1140" y="145" width="14" height="50"/><rect x="1170" y="125" width="14" height="90"/>
  </g>
  <g fill="#f59e0b">
    <rect x="1220" y="135" width="14" height="70"/><rect x="1250" y="115" width="14" height="110"/><rect x="1280" y="150" width="14" height="40"/><rect x="1310" y="125" width="14" height="90"/>
  </g>
  <!-- labels -->
  <text x="490" y="330" text-anchor="middle" font-size="30" fill="#5d5a7a">Already heard: kept as compressed state, not replayed</text>
  <text x="1070" y="330" text-anchor="middle" font-size="30" fill="#3923c7" font-weight="700">Being decoded now</text>
  <text x="1265" y="380" text-anchor="middle" font-size="28" fill="#b36b00" font-weight="700">Lookahead</text>
  <text x="1520" y="330" text-anchor="middle" font-size="30" fill="#5d5a7a">Not arrived yet</text>
  <text x="1265" y="416" text-anchor="middle" font-size="24" fill="#b36b00">a few hundred ms the model waits for</text>
  <!-- time axis -->
  <line x1="40" y1="40" x2="1710" y2="40" stroke="#d9d7ea" stroke-width="3"/>
  <text x="40" y="24" font-size="24" fill="#5d5a7a">time</text>
  <polygon points="1710,40 1690,30 1690,50" fill="#d9d7ea"/>
</svg>
<p class="note">Longer lookahead means better guesses and more delay. That trade-off is the whole design problem.</p>
```
Here is what the model is working with at any given moment. Everything to the left it has already heard. It doesn't replay that audio. It keeps a compressed internal state that summarises it, which is how it remembers context without the cost growing forever.

In the middle, highlighted in purple, is the chunk being decoded right now. And just to the right of that is a small lookahead window, in orange. The model deliberately waits for a little bit of future audio before deciding on the current words, because the end of a word often depends on the start of the next one.

That lookahead is the central trade off in streaming recognition. Give the model more future context and it guesses better, but every extra hundred milliseconds of lookahead is a hundred milliseconds the user waits. Streaming models are trained specifically to do well with a short window, which is a different skill from transcribing a finished file.

## Partials and finals
```slide
<div class="timeline">
  <div><span class="t">0.4 s</span><span class="txt"><mark>smoke</mark></span><span class="tag">partial</span></div>
  <div><span class="t">0.7 s</span><span class="txt">smoke <mark>from</mark></span><span class="tag">partial</span></div>
  <div><span class="t">1.1 s</span><span class="txt">smoke from <mark>hundreds of</mark></span><span class="tag">partial</span></div>
  <div><span class="t">1.9 s</span><span class="txt">smoke from hundreds of <mark>wildfires in canada</mark></span><span class="tag">partial</span></div>
  <div class="final"><span class="t">2.6 s</span><span class="txt">Smoke from hundreds of wildfires in Canada.</span><span class="tag">final</span></div>
</div>
<p class="note">Partials are fast and may change. The final arrives once the model decides the turn has ended, formatted and punctuated.</p>
```
The messages coming back come in two flavours. Partials arrive every few hundred milliseconds while someone is speaking. Each one is the model's current best guess at the whole utterance so far, and a later partial can change earlier words as more audio arrives.

Then, when the model decides the speaker has finished their turn, it sends a final. The final is the version you should keep. It's punctuated, capitalised, numbers are formatted, and it won't change.

Deciding when a turn has ended is called endpointing. The simple approach is to wait for a stretch of silence. Better systems also look at the words themselves, so a pause after "I'd like to book a table for" is treated as mid sentence, while a pause after "thanks, that's all" ends the turn quickly. This matters enormously for voice agents, because the agent can't start replying until the final arrives.

## Where the time goes
```slide
<div class="bars">
  <div class="bar muted" style="--w:6%"><span>Capturing one audio chunk</span><i></i><em>~50 ms</em></div>
  <div class="bar muted" style="--w:8%"><span>Network, client to server</span><i></i><em>20–80 ms</em></div>
  <div class="bar" style="--w:22%"><span>Model: lookahead plus compute</span><i></i><em>100–300 ms</em></div>
  <div class="bar warm" style="--w:60%"><span>Endpointing: waiting to be sure the turn ended</span><i></i><em>300–800 ms</em></div>
</div>
<p class="note">Word latency is what the leaderboard measures. Turn latency is what a caller feels. They're different numbers, and the second one is usually bigger.</p>
```
People talk about latency as one number, but it's really a stack of waits. Capturing a chunk of audio costs about fifty milliseconds. Sending it over the network costs a few tens more. The model itself, including its lookahead, typically adds one to three hundred milliseconds before a word shows up.

Then comes the big one. Deciding that the turn has ended means waiting long enough to be confident the person isn't just pausing. That is often the largest wait in the whole system, and it's a tuning decision as much as a model property.

So when you compare systems, ask which latency is being quoted. Time to a word appearing, or time to a usable final at the end of a turn. For live captions the first matters. For a voice agent, the second is what the caller actually feels.

## What hurts accuracy in streaming
```slide
<div class="cols-4">
  <div class="card"><h3>No second pass</h3>Once a word is final, it's final. A file transcriber can revise the whole sentence at the end; a streaming one commits as it goes.</div>
  <div class="card"><h3>Noise and crosstalk</h3>Background noise, two people at once, or a weak microphone give the model less signal in its short window.</div>
  <div class="card"><h3>Names and jargon</h3>Rare words are guessed from a few hundred milliseconds of sound. Supplying expected terms up front helps a lot.</div>
  <div class="card"><h3>Phone audio</h3>8 kHz telephone lines drop the high frequencies that distinguish sounds like S and F.</div>
</div>
```
A few things make streaming harder than transcribing a recording, and knowing them helps you set expectations.

First, there is no second pass. A file transcriber can look at the entire sentence before writing anything down. A streaming model commits to words as it goes, so a wrong early guess can survive.

Second, noise and crosstalk hit harder, because the model has a short window of audio to work from and can't lean on the rest of the recording to recover.

Third, rare words. Product names, drug names, people's names. The model is guessing them from a few hundred milliseconds of sound. Telling the system which terms to expect, before the call starts, makes a real difference.

And fourth, telephone audio. Phone lines carry eight thousand samples a second, which throws away the high frequencies that separate similar sounds. Expect lower accuracy on calls than on a laptop microphone, whichever system you use.

## Recap
```slide
<div class="steps">
  <div>Audio goes up a WebSocket in small chunks; text comes back down the same connection.</div>
  <div>The model decodes a short window with a little lookahead, keeping earlier audio as state.</div>
  <div>Partials are fast and can change. Finals are formatted and arrive when the turn ends.</div>
  <div>Latency is a stack: chunking, network, model, and the wait to detect end of turn.</div>
  <div>Streaming is harder than files: no second pass, short context, and phone audio is lossy.</div>
</div>
```
To recap. Audio goes up a WebSocket in small chunks and text comes back down the same connection, continuously.

The model decodes a short window of audio with a small lookahead, and remembers what came before as compressed state.

Partials are quick and provisional. Finals are formatted and arrive once the system decides the turn has ended.

Latency is a stack of waits, and the end of turn decision is usually the biggest piece.

And streaming is simply a harder problem than transcribing a file, which is why the same vendor's streaming and batch accuracy numbers are never quite the same.
