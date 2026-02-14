try:
    import redis.asyncio
    print("redis.asyncio installed")
except ImportError:
    print("redis.asyncio NOT installed")

try:
    import google.genai
    print("google.genai installed")
except ImportError:
    print("google.genai NOT installed")
