"use strict";
/* Sanjaya v6.0 · Why Sanjaya: the motivation behind the app, and its author's signature.
   The text lives here so it can be edited without touching the rest of the app. */
window.ATLASAbout = (() => {
  const AUTHOR = "Ambarish Moharil";
  const YEAR = "2026";
  function layout() {
    return `<article class="abPage">
      <header class="abHero">
        <img class="abEmblem" src="/brand/sanjaya-emblem.png" alt="The Sanjaya emblem: an eye with a fine brushed brow, its reins drawn as circuit traces and its pupil as a network">
        <p class="abDeva" lang="sa">सञ्जय</p>
        <h1>Sanjaya</h1>
        <p class="abLine">To gather, distinguish and present honest accounts of the world.</p>
      </header>

      <figure class="abVerse">
        <blockquote lang="sa-Latn"><p>dharma-kṣetre kuru-kṣetre samavetā yuyutsavaḥ</p><p>māmakāḥ pāṇḍavāś caiva kim akurvata sañjaya</p></blockquote>
        <figcaption>“On the field of dharma, at Kurukshetra, gathered and eager to fight: what did my sons and the sons of Pandu do, Sanjaya?”<span>Bhagavad Gita 1.1. The king's first question, and the first verse of the Gita.</span></figcaption>
      </figure>

      <section class="abText">
        <h2>The charioteer who could see</h2>
        <p>In the Mahabharata, Sanjaya is charioteer and counsellor to Dhritarashtra, the blind king of Hastinapura. Before the war at Kurukshetra, the sage Vyasa grants Sanjaya divine sight so that he can tell the king everything that happens on the battlefield, as it happens.</p>
        <p>Dhritarashtra is blind twice over: in his eyes, and in his love for his sons, which keeps him from seeing what they do. Sanjaya does not soften the account for him. He describes what he sees on both sides, the courage and the cruelty, the victories and the losses, and he does not bend the telling to please his king. It is that honest account, not comfort, that moves the king to look inward and face what has been done.</p>

        <h2>What this app tries to do</h2>
        <div class="abThree">
          <div><h3>Gather</h3><p>Reporting from India and the world, official sources, broadcasters, research and reference, collected on your own computer, with every source named.</p></div>
          <div><h3>Distinguish</h3><p>Who is reporting, from which side of the spectrum, behind which paywall; which accounts are the same story, which are related, and who hasn't covered it at all.</p></div>
          <div><h3>Present</h3><p>Never invent a headline. Show where every account comes from. Cite every sentence a model writes, and mark where your own judgement has changed a rating.</p></div>
        </div>

        <h2>A note on our own blindness</h2>
        <p>Every reader is a little like Dhritarashtra. What we are attached to shapes what we want to hear. An app can't take that away. What it can do is show the whole field, say plainly where each account comes from, and leave the reflection to us. That is why you can recalibrate the left–right gauge yourself: your reading is yours to make, and Sanjaya will always mark it as yours and keep the published rating in view.</p>

        <h2>The emblem</h2>
        <p>The emblem joins the two things Sanjaya was: the charioteer who held the reins, and the one given the sight to see for someone else.</p>
        <dl class="abParts">
          <div><dt>The eye</dt><dd>Drawn in the manner of Indian painting, with a fine brushed brow and a long kohl line. It is a human eye, not a camera or a watchful symbol. It looks a little past you, out at the world, because its job is to see on your behalf, as Sanjaya saw for the king.</dd></div>
          <div><dt>The reins</dt><dd>Drawn as circuit traces. They come in from the edge, from beyond the frame, the way accounts arrive from many places. They run taut and parallel; a charioteer's skill is restraint, keeping many lines steady without letting any pull the chariot off course. Some feed the eye. Others carry on past it, because an account is meant to be passed on.</dd></div>
          <div><dt>The pupil</dt><dd>A network: many nodes, every one connected, all converging on a single amber centre. Many sources, held together, become one sight. The centre is the honest account; the nodes around it keep it honest. Read another way, the network is also a chariot wheel, turning in the charioteer's eye.</dd></div>
          <div><dt>The balance</dt><dd>Heritage and the present in one figure: an ancient way of drawing the eye, built from today's means of gathering. The amber is the colour of lamplight on a manuscript; the deep blue-green is the night in which the account is told. Amber is also the colour Sanjaya uses for your own judgements, such as the lean ratings you set yourself.</dd></div>
        </dl>

        <h2>Why the name</h2>
        <p>This app began as Atlas, and its code still carries that name. I renamed it Sanjaya as a tribute to the Mahabharata, which has taught me so much in my life, and to the idea at its heart that the person who tells you about the world owes you the truth, especially the parts you would rather not hear.</p>
      </section>

      <footer class="abSign">
        <p class="abSignature">${AUTHOR}</p>
        <p class="fine">Made by ${AUTHOR}, ${YEAR} · MIT licence · <a href="https://github.com/a-moharil/Atlas" target="_blank" rel="noopener noreferrer">Source code ↗</a></p>
      </footer>
    </article>`;
  }
  return { layout, mount() {}, AUTHOR };
})();
