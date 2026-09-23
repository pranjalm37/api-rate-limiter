import redis.exceptions

# Which redis.asyncio exceptions actually mean "Redis is unreachable" --
# confirmed empirically (not just from the class hierarchy), against
# redis-py 5.0.8:
#
#   - Connection refused (nothing listening on the port)  -> ConnectionError
#   - DNS resolution failure (bad hostname)                -> ConnectionError
#   - Unreachable/hanging host (socket-level timeout)      -> TimeoutError
#
# ConnectionError and TimeoutError are siblings (both extend RedisError
# directly, neither extends the other), so both need to be caught -- one
# alone misses a real failure mode.
#
# Deliberately NOT catching RedisError broadly: that base class also
# covers ResponseError and similar cases where Redis is reachable and
# healthy but something is wrong with how we're using it (bad command,
# wrong data type for a key, etc.). Those are real bugs in this app, not
# "Redis is down" -- silently falling back to memory would mask them
# instead of surfacing them.
REDIS_CONNECTION_ERRORS = (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError)
