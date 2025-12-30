from youtube_transcript_api import YouTubeTranscriptApi

# https://www.youtube.com/watch?v=r7tov49OT3Y: Watch THESE CRYPTOS In 2026!!
video_id = "r7tov49OT3Y"
ytt_api = YouTubeTranscriptApi()
fetched_transcript = ytt_api.fetch(video_id)

# text만 추출해서 하나의 문자열로 결합
full_text = " ".join([snippet.text for snippet in fetched_transcript])

print(full_text)