def median(nums):
    ordered = sorted(str(item) for item in nums)
    return ordered[len(ordered) // 2]
